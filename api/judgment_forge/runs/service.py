"""
为何存在：研判 run 用例层——把「启动 / HITL 决定 / 取消 / 查询 / Trace / 取备忘录」
        与 HTTP、图细节解耦。
谁调用：runs.routes。
调用谁：RunRepository；projects.repository；build_judgment_graph（MemorySaver + invoke /
        Command(resume=…)）；materials / provider / web 端口；runs.trace（绑定缓冲并 flush）。

检查点身份：MemorySaver 的 thread_id = str(run_id)。同一 RunService 实例上，
  首次 invoke 与之后的 Command(resume=…) 必须共用该 thread_id，才能从 interrupt
  处接续，而不是整张图从头重跑。

cancel 与 deny 的区别：
  - cancel：所有者放弃本次 run → 终态 cancelled；清 pending_hitl；不向图 resume；
    之后 hitl 决定一律拒绝（已不在 waiting_for_human）。
  - deny：人机闸门上的「否决」决定 → 仍用 Command(resume="deny") 从检查点续跑，
    图继续走材料-only / 无清单等路径，最终 completed（或 failed）。

Trace（工单 11）：
  - 谁发出：graph 节点包装、nodes 内工具/打回、agent_chat 的 llm、本层 HITL/cancel
  - 落何处：bind_trace_buffer → TraceBuffer → update_status(append_trace_events)
  - API：list_trace_for_owner / list_events_for_owner 按 seq 有序返回（服务时间线 UI）

HITL 时序（工单 08 web + 工单 09 checklist + 工单 10 cancel/resume）：
  1) start → insert queued（含 produce_checklist）→ running → graph.invoke（thread_id=run_id）
  2) web_gate interrupt → status=waiting_for_human，写 pending_hitl + hitl/trace 事件；API 返回
  3) POST hitl(gate=web, approve|deny) → Command(resume=decision) 续跑
  4) 若 produce_checklist：Writer 起草后 checklist_gate 再 interrupt（第二道硬闸）
  5) POST hitl(gate=checklist, approve|deny) → 批准则 checklist 并进 memo JSONB；
     拒绝则仅备忘录、无清单；opt-out 从不进入步骤 4 的 interrupt
  6) 成功：写 memo + completed；失败：failed（对外 error_message 经 _safe_error_message）
  任意 waiting_for_human / running 可 POST cancel → cancelled（不 resume）
  故意不做外部写入：本层只 upsert decision_memos，不创建 GitHub/Jira 工单。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from judgment_forge.materials.service import MaterialService
from judgment_forge.projects.repository import ProjectRepository
from judgment_forge.provider.port import ChatProvider
from judgment_forge.runs.graph import build_judgment_graph
from judgment_forge.runs.repository import RunRepository
from judgment_forge.runs.state import (
    PublicDecisionMemo,
    memo_from_dict,
    memo_to_dict,
)
from judgment_forge.runs.trace import TraceBuffer, bind_trace_buffer, utc_now_iso
from judgment_forge.settings import Settings
from judgment_forge.web.port import WebSearchPort


@dataclass(frozen=True)
class PublicRun:
    id: UUID
    project_id: UUID
    question: str
    produce_checklist: bool
    web_enabled: bool
    status: str
    error_message: str | None
    critic_bounce_count: int
    pending_hitl: dict[str, Any] | None
    hitl_events: tuple[dict[str, Any], ...]


class RunError(Exception):
    """run 领域错误基类。"""


class RunNotFoundError(RunError):
    """run 对当前用户不可见或不存在（与跨用户同形）。"""


class ProjectNotFoundForRunError(RunError):
    """项目不可见时禁止开跑 / 查询。"""


class MemoNotFoundError(RunError):
    """备忘录尚未产出或不属于该用户。"""


class HitlNotPendingError(RunError):
    """run 当前不在等待该闸门的人机决定。"""


class HitlGateMismatchError(RunError):
    """提交的 gate 与 pending_hitl 不一致。"""


class RunNotCancellableError(RunError):
    """run 不在 running / waiting_for_human，无法取消。"""


# 对外安全文案：不暴露堆栈、密钥、连接串。
_SAFE_FAILED_MESSAGE = "Run failed; see server logs for details."
_SAFE_CANCELLED_MESSAGE = "Run was cancelled by the owner."
_CANCELLABLE_STATUSES = frozenset({"running", "waiting_for_human"})


class RunService:
    """启动图、处理 HITL resume / cancel、查询状态与备忘录。"""

    def __init__(
        self,
        settings: Settings,
        *,
        chat_provider: ChatProvider,
        material_service: MaterialService,
        web_search: WebSearchPort,
    ) -> None:
        self._settings = settings
        self._repo = RunRepository(settings)
        self._projects = ProjectRepository(settings)
        self._provider = chat_provider
        self._materials = material_service
        self._web_search = web_search
        # 进程内 checkpointer：同一 RunService 上 thread_id=run_id 才能 resume。
        self._checkpointer = MemorySaver()
        self._graph = build_judgment_graph(
            chat_provider,
            material_service,
            web_search,
            checkpointer=self._checkpointer,
        )

    def start(
        self,
        owner_id: UUID,
        project_id: UUID,
        question: str,
        *,
        produce_checklist: bool = False,
    ) -> PublicRun:
        """
        所有者启动 run：web_enabled 恒 False，图跑到 web_gate 即 interrupt。

        produce_checklist 写入 run 行并注入图初始状态；为真时 Writer 之后还会停在
        checklist_gate。返回多为 waiting_for_human；人批后再经 decide_hitl 续跑。
        """
        cleaned = question.strip()
        if not cleaned:
            raise ValueError("question must not be empty")
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForRunError(str(project_id))

        run_id = uuid4()
        self._repo.insert_queued(
            run_id=run_id,
            project_id=project_id,
            owner_id=owner_id,
            question=cleaned,
            produce_checklist=produce_checklist,
        )
        return self._invoke_or_resume(run_id, owner_id, project_id, input_payload=None)

    def decide_hitl(
        self,
        owner_id: UUID,
        project_id: UUID,
        run_id: UUID,
        *,
        gate: str,
        decision: str,
    ) -> PublicRun:
        """
        接收人机决定的用例入口（对应 POST .../hitl）。

        校验 waiting_for_human + pending gate 后，用 Command(resume=decision) 续跑 checkpoint。
        这是接续而非整图重跑：thread_id 仍是 run_id，LangGraph 从 interrupt 节点返回处继续。
        注意：deny 仍会 resume；若要放弃整次 run，应走 cancel，而不是 deny。
        """
        if decision not in ("approve", "deny"):
            raise ValueError("decision must be approve or deny")
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForRunError(str(project_id))
        row = self._repo.get_for_owner(run_id, project_id, owner_id)
        if row is None:
            raise RunNotFoundError(str(run_id))
        if row.status != "waiting_for_human" or not row.pending_hitl:
            raise HitlNotPendingError(str(run_id))
        pending_gate = str(row.pending_hitl.get("gate") or "")
        if pending_gate != gate:
            raise HitlGateMismatchError(
                f"pending gate is {pending_gate!r}, got {gate!r}"
            )

        decided_at = utc_now_iso()
        hitl_event = {
            "kind": "hitl",
            "gate": gate,
            "decision": decision,
            "at": decided_at,
        }
        self._repo.update_status(
            run_id,
            owner_id,
            status="running",
            clear_pending_hitl=True,
            append_hitl_event=hitl_event,
            append_trace_events=[hitl_event],
        )
        return self._invoke_or_resume(
            run_id,
            owner_id,
            project_id,
            input_payload=Command(resume=decision),
        )

    def cancel(
        self, owner_id: UUID, project_id: UUID, run_id: UUID
    ) -> PublicRun:
        """
        所有者取消进行中的 run（running 或 waiting_for_human）→ cancelled。

        与 deny 不同：不向图 Command(resume=…)，检查点被遗弃；清 pending_hitl。
        终态后不可再 hitl / cancel。
        """
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForRunError(str(project_id))
        row = self._repo.get_for_owner(run_id, project_id, owner_id)
        if row is None:
            raise RunNotFoundError(str(run_id))
        if row.status not in _CANCELLABLE_STATUSES:
            raise RunNotCancellableError(str(run_id))

        cancel_event = {
            "kind": "cancelled",
            "at": utc_now_iso(),
        }
        updated = self._repo.update_status(
            run_id,
            owner_id,
            status="cancelled",
            error_message=_SAFE_CANCELLED_MESSAGE,
            clear_pending_hitl=True,
            append_hitl_event=cancel_event,
            append_trace_events=[cancel_event],
        )
        assert updated is not None
        return _to_public(updated)

    def get_for_owner(
        self, owner_id: UUID, project_id: UUID, run_id: UUID
    ) -> PublicRun:
        """查询 run 状态；非所有者 / 错项目 → RunNotFoundError。"""
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForRunError(str(project_id))
        row = self._repo.get_for_owner(run_id, project_id, owner_id)
        if row is None:
            raise RunNotFoundError(str(run_id))
        return _to_public(row)

    def list_events_for_owner(
        self, owner_id: UUID, project_id: UUID, run_id: UUID
    ) -> list[dict[str, Any]]:
        """返回有序全量时间线（与 list_trace_for_owner 同；兼容 /events）。"""
        return self.list_trace_for_owner(owner_id, project_id, run_id)

    def list_trace_for_owner(
        self, owner_id: UUID, project_id: UUID, run_id: UUID
    ) -> list[dict[str, Any]]:
        """
        所有者拉取有序 Run Trace；非所有者 → RunNotFoundError（路由 404）。

        事件含 node / tool / llm / hitl / critic_bounce / cancelled；按 seq 排序。
        """
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForRunError(str(project_id))
        row = self._repo.get_for_owner(run_id, project_id, owner_id)
        if row is None:
            raise RunNotFoundError(str(run_id))
        return sorted(row.trace_events, key=lambda e: int(e.get("seq") or 0))

    def get_memo_for_owner(
        self, owner_id: UUID, project_id: UUID, run_id: UUID
    ) -> PublicDecisionMemo:
        """读取完成态备忘录；缺失或越权 → MemoNotFoundError。"""
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForRunError(str(project_id))
        run = self._repo.get_for_owner(run_id, project_id, owner_id)
        if run is None:
            raise RunNotFoundError(str(run_id))
        memo_row = self._repo.get_memo_for_owner(run_id, project_id, owner_id)
        if memo_row is None:
            raise MemoNotFoundError(str(run_id))
        return memo_from_dict(memo_row.body)

    def _invoke_or_resume(
        self,
        run_id: UUID,
        owner_id: UUID,
        project_id: UUID,
        *,
        input_payload: Any,
    ) -> PublicRun:
        """
        首次 invoke 或 Command(resume=…)；若仍 interrupt 则停在 waiting_for_human。

        检查点身份：thread_id 固定为 run_id 字符串，与 MemorySaver 对齐——
        resume 时传入 Command(resume=decision) 而非初始 state，图从闸门节点接续。
        失败时 error_message 经 _safe_error_message，避免密钥/堆栈进入 API body。
        若并行 cancel 已把行标为 cancelled，本方法不再覆盖为 completed/failed/waiting。
        Trace：invoke 外包 bind_trace_buffer，段末把缓冲事件 append 进 trace_events
        （含 interrupt 停住前的节点/llm，以及本段 HITL requested）。
        """
        row = self._repo.get_for_owner(run_id, project_id, owner_id)
        assert row is not None
        if row.status == "cancelled":
            return _to_public(row)
        # skip_if_cancelled：避免并行 cancel 后本路径又把行改回 running。
        started = self._repo.update_status(
            run_id, owner_id, status="running", skip_if_cancelled=True
        )
        if started is None:
            cancelled = self._repo.get_for_owner(run_id, project_id, owner_id)
            assert cancelled is not None
            return _to_public(cancelled)

        config = {"configurable": {"thread_id": str(run_id)}}
        buf = TraceBuffer()
        try:
            with bind_trace_buffer(buf):
                if input_payload is None:
                    initial = {
                        "question": row.question,
                        "project_id": str(project_id),
                        "owner_id": str(owner_id),
                        "produce_checklist": row.produce_checklist,
                        "web_enabled": False,
                        "web_hitl_decision": None,
                        "plan": [],
                        "evidence": [],
                        "claims": [],
                        "critic_feedback": "",
                        "bounce_count": 0,
                        "ready_for_writer": False,
                        "memo": None,
                        "checklist_draft": None,
                        "checklist": None,
                        "checklist_hitl_decision": None,
                        "error": None,
                    }
                    result = self._graph.invoke(initial, config)
                else:
                    result = self._graph.invoke(input_payload, config)

                interrupts = (
                    result.get("__interrupt__") if isinstance(result, dict) else None
                )
                if interrupts:
                    payload = _interrupt_payload(interrupts)
                    gate = str(payload.get("gate") or "web")
                    default_prompt = (
                        "是否定稿并保存本次行动清单？（拒绝则仅保留决策备忘录）"
                        if gate == "checklist"
                        else "是否允许本次研判使用联网/搜索工具？"
                    )
                    pending = {
                        "gate": gate,
                        "prompt": str(payload.get("prompt") or default_prompt),
                    }
                    hitl_event = {
                        "kind": "hitl",
                        "gate": pending["gate"],
                        "phase": "requested",
                        "at": utc_now_iso(),
                        "prompt": pending["prompt"],
                    }
                    buf.emit(**hitl_event)
                    updated = self._repo.update_status(
                        run_id,
                        owner_id,
                        status="waiting_for_human",
                        pending_hitl=pending,
                        append_hitl_event=hitl_event,
                        append_trace_events=buf.drain(),
                        skip_if_cancelled=True,
                    )
                    if updated is None:
                        cancelled = self._repo.get_for_owner(
                            run_id, project_id, owner_id
                        )
                        assert cancelled is not None
                        return _to_public(cancelled)
                    return _to_public(updated)

                memo = result.get("memo") if isinstance(result, dict) else None
                if not memo:
                    raise RuntimeError("writer produced no memo")
                bounce = int(result.get("bounce_count") or 0)
                web_enabled = bool(result.get("web_enabled"))
                # 清单仅在 checklist_gate 批准后出现于 result["checklist"]；
                # 拒绝 / opt-out 为 None——并进 memo JSONB，不写外部系统。
                body = memo_to_dict(memo)
                checklist = result.get("checklist") if isinstance(result, dict) else None
                if isinstance(checklist, list) and checklist:
                    body["checklist"] = [
                        str(item) for item in checklist if str(item).strip()
                    ]
                else:
                    body.pop("checklist", None)
                self._repo.upsert_memo(
                    memo_id=uuid4(),
                    run_id=run_id,
                    owner_id=owner_id,
                    body=body,
                )
                updated = self._repo.update_status(
                    run_id,
                    owner_id,
                    status="completed",
                    critic_bounce_count=bounce,
                    web_enabled=web_enabled,
                    clear_pending_hitl=True,
                    append_trace_events=buf.drain(),
                    skip_if_cancelled=True,
                )
                if updated is None:
                    cancelled = self._repo.get_for_owner(run_id, project_id, owner_id)
                    assert cancelled is not None
                    return _to_public(cancelled)
        except Exception as exc:  # noqa: BLE001 — 边界：图失败收成 failed
            pending_trace = buf.drain()
            updated = self._repo.update_status(
                run_id,
                owner_id,
                status="failed",
                error_message=_safe_error_message(exc),
                clear_pending_hitl=True,
                append_trace_events=pending_trace or None,
                skip_if_cancelled=True,
            )
            if updated is None:
                cancelled = self._repo.get_for_owner(run_id, project_id, owner_id)
                assert cancelled is not None
                return _to_public(cancelled)
        assert updated is not None
        return _to_public(updated)


def _safe_error_message(exc: BaseException) -> str:
    """
    把异常收成可对外的通用短句：不含堆栈、密钥、连接串或内部细节。

    意图：failed 的 API body 对用户安全；细节只留在服务端日志（此处不回传原文）。
    """
    _ = exc
    return _SAFE_FAILED_MESSAGE


def _interrupt_payload(interrupts: Any) -> dict[str, Any]:
    """从 LangGraph __interrupt__ 列表取出第一个 payload dict（web 或 checklist）。"""
    first = interrupts[0]
    value = getattr(first, "value", first)
    return dict(value) if isinstance(value, dict) else {"gate": "web"}


def _to_public(row) -> PublicRun:
    return PublicRun(
        id=row.id,
        project_id=row.project_id,
        question=row.question,
        produce_checklist=row.produce_checklist,
        web_enabled=row.web_enabled,
        status=row.status,
        error_message=row.error_message,
        critic_bounce_count=row.critic_bounce_count,
        pending_hitl=row.pending_hitl,
        hitl_events=tuple(row.hitl_events),
    )
