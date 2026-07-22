"""
为何存在：在 Postgres 上声明并幂等创建业务表，避免手工 DDL 成为本地启动门槛。
谁调用：create_app 启动时、以及依赖库连接的仓储层（间接经 ensure_schema）。
调用谁：judgment_forge.db.get_connection / Settings。

含研判 run：judgment_runs（状态机行，含 waiting_for_human / pending_hitl /
hitl_events / trace_events）与 decision_memos；由 runs.repository 读写，图节点不直接 SQL。
trace_events：工单 11 的有序时间线（node/tool/llm/HITL/critic_bounce）；
  由 service 在编排钩子 flush，API /trace 与 /events 按 seq 读出。
"""

from __future__ import annotations

from judgment_forge.db import get_connection
from judgment_forge.settings import Settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- projects：多租户边界的数据根——owner_id 绑定所有者；
-- 业务读写必须带 owner_id 过滤（见 projects.repository），禁止仅凭 id 跨用户访问。
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS projects_owner_id_idx ON projects (owner_id);

-- materials：项目内证据包元数据；status 走 processing → ready|failed。
-- owner_id 冗余以便与 projects 一样用所有者过滤，删除后级联清 chunks。
CREATE TABLE IF NOT EXISTS materials (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS materials_project_owner_idx
    ON materials (project_id, owner_id);

-- material_chunks：入库切块；location_hint 供引用锚点（page/section/paragraph）。
-- 检索走 Postgres 全文（tsvector），避免 v1 硬依赖外部向量 SaaS；
-- 后续 Researcher 经 MaterialService.search 读本表，不直连 SQL。
CREATE TABLE IF NOT EXISTS material_chunks (
    id UUID PRIMARY KEY,
    material_id UUID NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    location_hint TEXT NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
);

CREATE INDEX IF NOT EXISTS material_chunks_tsv_idx
    ON material_chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS material_chunks_project_owner_idx
    ON material_chunks (project_id, owner_id);

-- judgment_runs：一次研判的生命周期行；status 含 waiting_for_human（HITL web/checklist 闸门）。
-- produce_checklist：启动时清单开关，注入图状态；web_enabled 默认 FALSE。
-- pending_hitl / hitl_events：闸门快照与 HITL 子集；trace_events：完整有序时间线（工单 11）。
-- 清单定稿进 decision_memos.body.checklist。
-- 图本身不写库：由 runs.service 在 invoke / resume 前后更新本表并落 memo（无外部 tracker）。
CREATE TABLE IF NOT EXISTS judgment_runs (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    produce_checklist BOOLEAN NOT NULL DEFAULT FALSE,
    web_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL,
    error_message TEXT,
    critic_bounce_count INTEGER NOT NULL DEFAULT 0,
    pending_hitl JSONB,
    hitl_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    trace_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS judgment_runs_project_owner_idx
    ON judgment_runs (project_id, owner_id);

-- decision_memos：成功完成后的决策备忘录（JSONB：四段 + claims/anchors；
-- 可选 checklist 仅在 opt-in 且第二道闸批准后出现）。
CREATE TABLE IF NOT EXISTS decision_memos (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL UNIQUE REFERENCES judgment_runs(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS decision_memos_owner_idx
    ON decision_memos (owner_id);
"""

# 已有库升级：放宽 status 约束、补 HITL/trace 列（CREATE TABLE IF NOT EXISTS 不会改旧表）。
_MIGRATE_SQL = """
ALTER TABLE judgment_runs DROP CONSTRAINT IF EXISTS judgment_runs_status_check;
ALTER TABLE judgment_runs
    ADD CONSTRAINT judgment_runs_status_check
    CHECK (status IN (
        'queued', 'running', 'waiting_for_human',
        'completed', 'failed', 'cancelled'
    ));
ALTER TABLE judgment_runs
    ADD COLUMN IF NOT EXISTS pending_hitl JSONB;
ALTER TABLE judgment_runs
    ADD COLUMN IF NOT EXISTS hitl_events JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE judgment_runs
    ADD COLUMN IF NOT EXISTS trace_events JSONB NOT NULL DEFAULT '[]'::jsonb;
-- 旧库：把已有 HITL 事件回填进 trace（仅当 trace 仍为空），避免升级后时间线空白。
UPDATE judgment_runs
SET trace_events = hitl_events
WHERE coalesce(jsonb_array_length(trace_events), 0) = 0
  AND coalesce(jsonb_array_length(hitl_events), 0) > 0;
"""


def ensure_schema(settings: Settings) -> None:
    """幂等创建 users/sessions/projects/materials/chunks/runs/memos 表，并迁移 HITL/trace 列。"""
    with get_connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)
            cur.execute(_MIGRATE_SQL)
        conn.commit()
