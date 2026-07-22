"""
为何存在：验收 HITL 联网闸门（工单 08）——默认禁网、尝试用网暂停、批/拒路径、
        假 web spy 证明批准前未调网；落在 JudgmentForge HTTP API 缝。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app；app.state.web_search（FakeWeb spy）。
"""

from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from judgment_forge.app import create_app
from judgment_forge.settings import Settings
from judgment_forge.web.fake import FakeWebSearch


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
        json={"name": "HITL web", "description": "gate"},
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


def _start_run(
    client: TestClient, headers: dict[str, str], project_id: str, question: str
) -> dict:
    started = client.post(
        f"/projects/{project_id}/runs",
        headers=headers,
        json={"question": question},
    )
    assert started.status_code == 201
    return started.json()


def test_new_run_web_disabled_and_pauses_for_web_hitl():
    """新 run 默认禁网；图尝试启用联网时进入 waiting_for_human，且批准前不调 web。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(
        client,
        headers,
        project_id,
        "LangGraph checkpoints make HITL resume possible.\n",
    )
    spy: FakeWebSearch = client.app.state.web_search

    run = _start_run(
        client,
        headers,
        project_id,
        "Should we enable web tools for this judgment?",
    )
    assert run["web_enabled"] is False
    assert run["status"] == "waiting_for_human"
    assert run["pending_hitl"]["gate"] == "web"
    assert spy.call_count == 0

    status = client.get(
        f"/projects/{project_id}/runs/{run['id']}",
        headers=headers,
    ).json()
    assert status["status"] == "waiting_for_human"
    assert status["web_enabled"] is False
    assert spy.call_count == 0

    events = client.get(
        f"/projects/{project_id}/runs/{run['id']}/events",
        headers=headers,
    )
    assert events.status_code == 200
    body = events.json()
    assert any(
        e.get("kind") == "hitl" and e.get("gate") == "web" for e in body["events"]
    )


def test_approve_enables_web_with_url_and_timestamp_citations():
    """批准后启用 web；引用含 URL + 检索时间；spy 仅在批准后被调用。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(
        client,
        headers,
        project_id,
        "Materials-only note about orchestration tradeoffs.\n",
    )
    spy: FakeWebSearch = client.app.state.web_search
    assert spy.call_count == 0

    run = _start_run(
        client,
        headers,
        project_id,
        "Compare self-build vs managed agent with external docs?",
    )
    assert run["status"] == "waiting_for_human"
    assert spy.call_count == 0

    decided = client.post(
        f"/projects/{project_id}/runs/{run['id']}/hitl",
        headers=headers,
        json={"gate": "web", "decision": "approve"},
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "completed"
    assert body["web_enabled"] is True
    assert spy.call_count >= 1

    memo = client.get(
        f"/projects/{project_id}/runs/{run['id']}/memo",
        headers=headers,
    ).json()
    web_anchors = [
        a
        for c in memo["claims"]
        for a in c.get("anchors") or []
        if a.get("url")
    ]
    assert len(web_anchors) >= 1
    for anchor in web_anchors:
        assert anchor["url"].startswith("http")
        assert anchor.get("retrieved_at")

    events = client.get(
        f"/projects/{project_id}/runs/{run['id']}/events",
        headers=headers,
    ).json()["events"]
    assert any(
        e.get("kind") == "hitl"
        and e.get("gate") == "web"
        and e.get("decision") == "approve"
        for e in events
    )


def test_deny_keeps_materials_only_and_still_completes_memo():
    """拒绝联网：web spy 始终未调用；材料-only 路径仍产出备忘录。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    material_id = _upload_notes(
        client,
        headers,
        project_id,
        "Self-building on LangGraph gives auditability of agent steps.\n",
    )
    spy: FakeWebSearch = client.app.state.web_search

    run = _start_run(
        client,
        headers,
        project_id,
        "Should we self-build orchestration?",
    )
    assert run["status"] == "waiting_for_human"
    assert spy.call_count == 0

    decided = client.post(
        f"/projects/{project_id}/runs/{run['id']}/hitl",
        headers=headers,
        json={"gate": "web", "decision": "deny"},
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "completed"
    assert body["web_enabled"] is False
    assert spy.call_count == 0

    memo = client.get(
        f"/projects/{project_id}/runs/{run['id']}/memo",
        headers=headers,
    ).json()
    for key in ("conclusion", "options", "risks_unknowns", "next_steps"):
        assert memo[key].strip()
    # 拒绝路径不应出现 web 锚点
    for claim in memo["claims"]:
        for anchor in claim.get("anchors") or []:
            assert not anchor.get("url")
            if claim["presented_as"] == "fact":
                assert anchor.get("material_id") == material_id

    events = client.get(
        f"/projects/{project_id}/runs/{run['id']}/events",
        headers=headers,
    ).json()["events"]
    assert any(
        e.get("kind") == "hitl"
        and e.get("gate") == "web"
        and e.get("decision") == "deny"
        for e in events
    )


def test_web_spy_never_called_before_approval():
    """显式用假 web spy 证明：批准前 call_count 恒为 0。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(client, headers, project_id, "Evidence snippet.\n")
    spy: FakeWebSearch = client.app.state.web_search

    run = _start_run(client, headers, project_id, "Need external sources?")
    assert spy.call_count == 0
    client.get(f"/projects/{project_id}/runs/{run['id']}", headers=headers)
    assert spy.call_count == 0
    # 错误 gate / 未决定前再查一次
    assert (
        client.post(
            f"/projects/{project_id}/runs/{run['id']}/hitl",
            headers=headers,
            json={"gate": "checklist", "decision": "approve"},
        ).status_code
        == 400
    )
    assert spy.call_count == 0
