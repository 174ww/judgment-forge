"""
为何存在：研判 run 与决策备忘录的持久化——把「图跑完的结果 / HITL / Trace / 取消」变成可查询行。
谁调用：runs.service（创建/更新状态/写备忘录/记录 HITL/cancel/flush trace/按所有者读取）。
调用谁：judgment_forge.db.get_connection、Settings。

多租户：凡按 id 读的 SQL 都带 owner_id；越权与真缺失同形（None）。
谁持久化：service 在图 invoke / resume / cancel 前后写 status、pending_hitl、
         hitl_events、trace_events、memo、error_message——图节点本身不碰数据库。
         cancelled 与 failed 的对外文案由 service 先消毒再写入 error_message。
         Trace：编排钩子先写入 TraceBuffer，段末经 append_trace_events 落 JSONB。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Json

from judgment_forge.db import get_connection
from judgment_forge.settings import Settings


@dataclass(frozen=True)
class RunRow:
    id: UUID
    project_id: UUID
    owner_id: UUID
    question: str
    produce_checklist: bool
    web_enabled: bool
    status: str
    error_message: str | None
    critic_bounce_count: int
    pending_hitl: dict[str, Any] | None
    hitl_events: list[dict[str, Any]]
    trace_events: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MemoRow:
    id: UUID
    run_id: UUID
    owner_id: UUID
    body: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any] | None:
    """把 JSONB/字符串收成 dict；None 保持 None（pending_hitl 空闲态）。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value)


def _as_list(value: Any) -> list[dict[str, Any]]:
    """把 JSONB 事件数组收成 list[dict]；缺省当空列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value)
    return [dict(item) for item in value]


def _run_from_row(row: dict) -> RunRow:
    return RunRow(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        question=row["question"],
        produce_checklist=row["produce_checklist"],
        web_enabled=row["web_enabled"],
        status=row["status"],
        error_message=row["error_message"],
        critic_bounce_count=row["critic_bounce_count"],
        pending_hitl=_as_dict(row.get("pending_hitl")),
        hitl_events=_as_list(row.get("hitl_events")),
        trace_events=_as_list(row.get("trace_events")),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


_RUN_RETURNING = """
    id, project_id, owner_id, question,
    produce_checklist, web_enabled, status,
    error_message, critic_bounce_count,
    pending_hitl, hitl_events, trace_events,
    created_at, updated_at
"""


class RunRepository:
    """judgment_runs / decision_memos 表读写；短连接 + 所有者过滤。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def insert_queued(
        self,
        *,
        run_id: UUID,
        project_id: UUID,
        owner_id: UUID,
        question: str,
        produce_checklist: bool,
    ) -> RunRow:
        """插入 queued run；web_enabled 固定 False（联网须经 HITL 批准）。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO judgment_runs (
                        id, project_id, owner_id, question,
                        produce_checklist, web_enabled, status
                    )
                    VALUES (%s, %s, %s, %s, %s, FALSE, 'queued')
                    RETURNING {_RUN_RETURNING}
                    """,
                    (run_id, project_id, owner_id, question, produce_checklist),
                )
                row = cur.fetchone()
            conn.commit()
        assert row is not None
        return _run_from_row(row)

    def update_status(
        self,
        run_id: UUID,
        owner_id: UUID,
        *,
        status: str,
        error_message: str | None = None,
        critic_bounce_count: int | None = None,
        web_enabled: bool | None = None,
        pending_hitl: dict[str, Any] | None = None,
        clear_pending_hitl: bool = False,
        append_hitl_event: dict[str, Any] | None = None,
        append_trace_events: list[dict[str, Any]] | None = None,
        skip_if_cancelled: bool = False,
    ) -> RunRow | None:
        """
        按所有者更新状态；可选写入 bounce、web_enabled、pending_hitl、
        追加 HITL 事件与/或一批 trace 事件。

        clear_pending_hitl=True 时把 pending_hitl 置空（人已做决定或已取消）。
        skip_if_cancelled=True 时若当前已是 cancelled 则不覆盖（invoke 收尾防竞态）。
        append_trace_events：为每条补全局 seq（接续已有 trace_events 长度）。
        """
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                numbered_trace: list[dict[str, Any]] | None = None
                if append_trace_events:
                    cur.execute(
                        """
                        SELECT coalesce(jsonb_array_length(trace_events), 0) AS n
                        FROM judgment_runs
                        WHERE id = %s AND owner_id = %s
                        """,
                        (run_id, owner_id),
                    )
                    meta = cur.fetchone()
                    base = int(meta["n"]) if meta else 0
                    numbered_trace = []
                    for offset, raw in enumerate(append_trace_events):
                        item = dict(raw)
                        item["seq"] = base + offset + 1
                        numbered_trace.append(item)

                cur.execute(
                    f"""
                    UPDATE judgment_runs
                    SET
                        status = %s,
                        error_message = %s,
                        critic_bounce_count = COALESCE(%s, critic_bounce_count),
                        web_enabled = COALESCE(%s, web_enabled),
                        pending_hitl = CASE
                            WHEN %s THEN NULL
                            WHEN %s::jsonb IS NOT NULL THEN %s::jsonb
                            ELSE pending_hitl
                        END,
                        hitl_events = CASE
                            WHEN %s::jsonb IS NOT NULL THEN
                                hitl_events || %s::jsonb
                            ELSE hitl_events
                        END,
                        trace_events = CASE
                            WHEN %s::jsonb IS NOT NULL THEN
                                trace_events || %s::jsonb
                            ELSE trace_events
                        END,
                        updated_at = now()
                    WHERE id = %s AND owner_id = %s
                      AND (NOT %s OR status <> 'cancelled')
                    RETURNING {_RUN_RETURNING}
                    """,
                    (
                        status,
                        error_message,
                        critic_bounce_count,
                        web_enabled,
                        clear_pending_hitl,
                        Json(pending_hitl) if pending_hitl is not None else None,
                        Json(pending_hitl) if pending_hitl is not None else None,
                        Json([append_hitl_event])
                        if append_hitl_event is not None
                        else None,
                        Json([append_hitl_event])
                        if append_hitl_event is not None
                        else None,
                        Json(numbered_trace) if numbered_trace is not None else None,
                        Json(numbered_trace) if numbered_trace is not None else None,
                        run_id,
                        owner_id,
                        skip_if_cancelled,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return _run_from_row(row)

    def get_for_owner(
        self, run_id: UUID, project_id: UUID, owner_id: UUID
    ) -> RunRow | None:
        """读取 run；必须同时匹配 project_id 与 owner_id。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    SELECT {_RUN_RETURNING}
                    FROM judgment_runs
                    WHERE id = %s AND project_id = %s AND owner_id = %s
                    """,
                    (run_id, project_id, owner_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return _run_from_row(row)

    def upsert_memo(
        self,
        *,
        memo_id: UUID,
        run_id: UUID,
        owner_id: UUID,
        body: dict[str, Any],
    ) -> MemoRow:
        """成功完成后写入（或覆盖）决策备忘录 JSONB。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO decision_memos (id, run_id, owner_id, body)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE
                    SET body = EXCLUDED.body
                    RETURNING id, run_id, owner_id, body
                    """,
                    (memo_id, run_id, owner_id, Json(body)),
                )
                row = cur.fetchone()
            conn.commit()
        assert row is not None
        body_val = row["body"]
        if isinstance(body_val, str):
            body_val = json.loads(body_val)
        return MemoRow(
            id=row["id"],
            run_id=row["run_id"],
            owner_id=row["owner_id"],
            body=dict(body_val),
        )

    def get_memo_for_owner(
        self, run_id: UUID, project_id: UUID, owner_id: UUID
    ) -> MemoRow | None:
        """
        取备忘录；JOIN run 以强制 project + owner 边界。

        他人 run_id → None（路由层 404）。
        """
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT m.id, m.run_id, m.owner_id, m.body
                    FROM decision_memos m
                    INNER JOIN judgment_runs r ON r.id = m.run_id
                    WHERE m.run_id = %s
                      AND m.owner_id = %s
                      AND r.project_id = %s
                      AND r.owner_id = %s
                    """,
                    (run_id, owner_id, project_id, owner_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        body_val = row["body"]
        if isinstance(body_val, str):
            body_val = json.loads(body_val)
        return MemoRow(
            id=row["id"],
            run_id=row["run_id"],
            owner_id=row["owner_id"],
            body=dict(body_val),
        )
