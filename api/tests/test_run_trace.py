"""
为何存在：验收 Run Trace API（工单 11）——有序时间线含节点/工具/HITL/Critic 打回，
        粗粒度 token/时延可测时出现；所有者可拉、跨用户拒绝。
        落在 JudgmentForge HTTP API 缝；FakeLLM 场景触发 HITL 与 critic-bounce。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app；测试内可重建带「首轮打回」的图。
"""

from __future__ import annotations

import io
import uuid
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from judgment_forge.app import create_app
from judgment_forge.materials.service import MaterialService
from judgment_forge.provider.fake import FakeLLM
from judgment_forge.provider.port import ChatProvider
from judgment_forge.runs.graph import _traced_node, route_after_critic
from judgment_forge.runs.nodes import (
    make_checklist_gate_node,
    make_critic_node,
    make_planner_node,
    make_researcher_node,
    make_web_gate_node,
    make_writer_node,
)
from judgment_forge.runs.service import RunService
from judgment_forge.runs.state import JudgmentState
from judgment_forge.settings import Settings
from judgment_forge.web.fake import FakeWebSearch
from judgment_forge.web.port import WebSearchPort


def _client() -> TestClient:
    return TestClient(create_app(Settings(llm_provider="fake")))


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _register_and_login(client: TestClient) -> dict[str, str]:
    email = _unique_email()
    password = "correct-horse-battery"
    assert (
        client.post(
            "/auth/register",
            json={"email": email, "password": password},
        ).status_code
        == 201
    )
    token = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project(client: TestClient, headers: dict[str, str]) -> str:
    created = client.post(
        "/projects",
        headers=headers,
        json={"name": "Trace", "description": "run trace"},
    )
    assert created.status_code == 201
    return created.json()["id"]


def _upload_notes(
    client: TestClient, headers: dict[str, str], project_id: str, text: str
) -> str:
    upload = client.post(
        f"/projects/{project_id}/materials",
        headers=headers,
        files={
            "file": (
                "notes.txt",
                io.BytesIO(text.encode("utf-8")),
                "text/plain",
            )
        },
    )
    assert upload.status_code == 201
    return upload.json()["id"]


def _build_graph_with_bounce_once_researcher(
    provider: ChatProvider,
    materials: MaterialService,
    web_search: WebSearchPort,
    *,
    checkpointer: MemorySaver,
):
    """
    测试专用图：Researcher 首轮故意产出无锚点 fact → Critic bounce；
    第二轮起走真实 Researcher，以便 FakeLLM 场景下出现 critic_bounce 事件。
    """
    real_researcher = make_researcher_node(provider, materials, web_search)
    calls = {"n": 0}

    def bounce_once_researcher(state: JudgmentState) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "evidence": [],
                "claims": [
                    {
                        "text": "无锚点却写成事实，应被 Critic 打回。",
                        "presented_as": "fact",
                        "anchors": [],
                    }
                ],
            }
        return real_researcher(state)

    graph = StateGraph(JudgmentState)
    graph.add_node("planner", _traced_node("planner", make_planner_node(provider)))
    graph.add_node("web_gate", _traced_node("web_gate", make_web_gate_node()))
    graph.add_node("researcher", _traced_node("researcher", bounce_once_researcher))
    graph.add_node("critic", _traced_node("critic", make_critic_node()))
    graph.add_node("writer", _traced_node("writer", make_writer_node(provider)))
    graph.add_node(
        "checklist_gate",
        _traced_node("checklist_gate", make_checklist_gate_node()),
    )
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "web_gate")
    graph.add_edge("web_gate", "researcher")
    graph.add_edge("researcher", "critic")
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"researcher": "researcher", "writer": "writer"},
    )
    graph.add_edge("writer", "checklist_gate")
    graph.add_edge("checklist_gate", END)
    return graph.compile(checkpointer=checkpointer)


def test_owner_can_fetch_ordered_trace_with_hitl_and_critic_bounce():
    """
    FakeLLM 金路径：HITL web 决定 + Critic 打回均出现在有序 /trace 中；
    可测时带粗粒度 latency / token 字段。
    """
    settings = Settings(llm_provider="fake")
    app = create_app(settings)
    provider = FakeLLM()
    materials = MaterialService(settings)
    web = FakeWebSearch()
    service = RunService(
        settings,
        chat_provider=provider,
        material_service=materials,
        web_search=web,
    )
    # 换上「首轮打回」图，仍共用同一 MemorySaver（HITL resume 需要）。
    service._graph = _build_graph_with_bounce_once_researcher(  # noqa: SLF001
        provider,
        materials,
        web,
        checkpointer=service._checkpointer,  # noqa: SLF001
    )
    app.state.run_service = service
    app.state.chat_provider = provider
    app.state.web_search = web
    client = TestClient(app)

    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(
        client,
        headers,
        project_id,
        "First-party traces make critic bounces inspectable.\n",
    )

    started = client.post(
        f"/projects/{project_id}/runs",
        headers=headers,
        json={"question": "Can we see HITL and critic bounce in the trace?"},
    )
    assert started.status_code == 201
    run = started.json()
    assert run["status"] == "waiting_for_human"
    run_id = run["id"]

    # 中途已应能看到 planner / web_gate / HITL requested。
    mid = client.get(
        f"/projects/{project_id}/runs/{run_id}/trace",
        headers=headers,
    )
    assert mid.status_code == 200
    mid_events = mid.json()["events"]
    assert any(
        e.get("kind") == "hitl"
        and e.get("gate") == "web"
        and e.get("phase") == "requested"
        for e in mid_events
    )
    assert any(e.get("kind") == "node" and e.get("name") == "planner" for e in mid_events)

    decided = client.post(
        f"/projects/{project_id}/runs/{run_id}/hitl",
        headers=headers,
        json={"gate": "web", "decision": "deny"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "completed"
    assert decided.json()["critic_bounce_count"] >= 1

    trace = client.get(
        f"/projects/{project_id}/runs/{run_id}/trace",
        headers=headers,
    )
    assert trace.status_code == 200
    events = trace.json()["events"]
    assert events == sorted(events, key=lambda e: e.get("seq", 0))

    kinds = [e.get("kind") for e in events]
    assert "hitl" in kinds
    assert "critic_bounce" in kinds
    assert "node" in kinds
    assert "tool" in kinds  # materials.search
    assert "llm" in kinds

    hitl_decided = [
        e
        for e in events
        if e.get("kind") == "hitl"
        and e.get("gate") == "web"
        and e.get("decision") == "deny"
    ]
    assert hitl_decided

    bounce = next(e for e in events if e.get("kind") == "critic_bounce")
    assert bounce.get("bounce_count", 0) >= 1

    # 粗粒度消耗：至少一类可测字段出现在 llm 或 node 事件上。
    measurable = [
        e
        for e in events
        if e.get("latency_ms") is not None
        or e.get("prompt_tokens") is not None
        or e.get("completion_tokens") is not None
    ]
    assert measurable

    # /events 与 /trace 同为有序全量时间线（工单 08 的 HITL 过滤仍可用）。
    events_alias = client.get(
        f"/projects/{project_id}/runs/{run_id}/events",
        headers=headers,
    )
    assert events_alias.status_code == 200
    assert events_alias.json()["events"] == events


def test_cross_user_cannot_fetch_another_users_trace():
    """跨用户拉 trace → 404（与真缺失同形）。"""
    client = _client()
    headers_a = _register_and_login(client)
    headers_b = _register_and_login(client)
    project_id = _create_project(client, headers_a)
    _upload_notes(client, headers_a, project_id, "Owner-only traces.\n")

    started = client.post(
        f"/projects/{project_id}/runs",
        headers=headers_a,
        json={"question": "Private trace?"},
    )
    assert started.status_code == 201
    run_id = started.json()["id"]

    denied = client.get(
        f"/projects/{project_id}/runs/{run_id}/trace",
        headers=headers_b,
    )
    assert denied.status_code == 404
    # 跨用户：项目边界先挡 → project not found；与真缺失同形 404。
    assert denied.json()["detail"] in ("project not found", "run not found")
