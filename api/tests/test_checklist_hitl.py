"""
为何存在：验收可选行动清单 + 第二道 HITL 闸门（工单 09）——仅 opt-in 才起草；
        定稿前 waiting；批准持久化 3–8 条；拒绝保留备忘录无清单；opt-out 永不产出；
        不创建外部工单。落在 JudgmentForge HTTP API 缝。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app。
"""

from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from judgment_forge.app import create_app
from judgment_forge.settings import Settings


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
        json={"name": "Checklist HITL", "description": "gate 2"},
    )
    assert created.status_code == 201
    return created.json()["id"]


def _upload_notes(
    client: TestClient, headers: dict[str, str], project_id: str, text: str
) -> None:
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


def _deny_web_then(
    client: TestClient, headers: dict[str, str], project_id: str, run_id: str
) -> dict:
    """过第一道联网闸（拒绝），便于用例聚焦清单闸。"""
    decided = client.post(
        f"/projects/{project_id}/runs/{run_id}/hitl",
        headers=headers,
        json={"gate": "web", "decision": "deny"},
    )
    assert decided.status_code == 200
    return decided.json()


def test_opt_in_pauses_for_checklist_gate_then_approve_persists_items():
    """opt-in：Writer 后暂停于 checklist 闸；批准 → 备忘录带 3–8 条清单。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(
        client,
        headers,
        project_id,
        "Self-building on LangGraph gives auditability of agent steps.\n",
    )

    started = client.post(
        f"/projects/{project_id}/runs",
        headers=headers,
        json={
            "question": "Should we self-build orchestration?",
            "produce_checklist": True,
        },
    )
    assert started.status_code == 201
    run = started.json()
    assert run["produce_checklist"] is True
    assert run["status"] == "waiting_for_human"
    assert run["pending_hitl"]["gate"] == "web"

    after_web = _deny_web_then(client, headers, project_id, run["id"])
    assert after_web["status"] == "waiting_for_human"
    assert after_web["pending_hitl"]["gate"] == "checklist"

    approved = client.post(
        f"/projects/{project_id}/runs/{run['id']}/hitl",
        headers=headers,
        json={"gate": "checklist", "decision": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"

    memo = client.get(
        f"/projects/{project_id}/runs/{run['id']}/memo",
        headers=headers,
    ).json()
    for key in ("conclusion", "options", "risks_unknowns", "next_steps"):
        assert memo[key].strip()
    checklist = memo.get("checklist")
    assert isinstance(checklist, list)
    assert 3 <= len(checklist) <= 8
    assert all(isinstance(item, str) and item.strip() for item in checklist)

    events = client.get(
        f"/projects/{project_id}/runs/{run['id']}/events",
        headers=headers,
    ).json()["events"]
    assert any(
        e.get("kind") == "hitl"
        and e.get("gate") == "checklist"
        and e.get("decision") == "approve"
        for e in events
    )


def test_opt_in_deny_keeps_memo_without_checklist():
    """opt-in 拒绝清单：备忘录仍完成，且无 checklist 字段/为空。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(
        client,
        headers,
        project_id,
        "Managed platforms ship faster for small teams.\n",
    )

    started = client.post(
        f"/projects/{project_id}/runs",
        headers=headers,
        json={
            "question": "Ship on managed agent first?",
            "produce_checklist": True,
        },
    )
    run_id = started.json()["id"]
    after_web = _deny_web_then(client, headers, project_id, run_id)
    assert after_web["pending_hitl"]["gate"] == "checklist"

    denied = client.post(
        f"/projects/{project_id}/runs/{run_id}/hitl",
        headers=headers,
        json={"gate": "checklist", "decision": "deny"},
    )
    assert denied.status_code == 200
    assert denied.json()["status"] == "completed"

    memo = client.get(
        f"/projects/{project_id}/runs/{run_id}/memo",
        headers=headers,
    ).json()
    for key in ("conclusion", "options", "risks_unknowns", "next_steps"):
        assert memo[key].strip()
    assert not memo.get("checklist")

    events = client.get(
        f"/projects/{project_id}/runs/{run_id}/events",
        headers=headers,
    ).json()["events"]
    assert any(
        e.get("kind") == "hitl"
        and e.get("gate") == "checklist"
        and e.get("decision") == "deny"
        for e in events
    )


def test_opt_out_never_emits_checklist_or_checklist_gate():
    """opt-out：过 web 闸后直接完成；无清单闸、备忘录无 checklist。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(
        client,
        headers,
        project_id,
        "First-party run traces help interviews explain multi-agent value.\n",
    )

    started = client.post(
        f"/projects/{project_id}/runs",
        headers=headers,
        json={
            "question": "Is first-party trace valuable?",
            "produce_checklist": False,
        },
    )
    run_id = started.json()["id"]
    assert started.json()["produce_checklist"] is False

    after_web = _deny_web_then(client, headers, project_id, run_id)
    assert after_web["status"] == "completed"
    assert after_web.get("pending_hitl") is None

    memo = client.get(
        f"/projects/{project_id}/runs/{run_id}/memo",
        headers=headers,
    ).json()
    assert not memo.get("checklist")

    events = client.get(
        f"/projects/{project_id}/runs/{run_id}/events",
        headers=headers,
    ).json()["events"]
    assert not any(e.get("gate") == "checklist" for e in events)
