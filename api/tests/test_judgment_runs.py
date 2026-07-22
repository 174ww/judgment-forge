"""
为何存在：验收最小研判 run（工单 07）——启动、四节点完成、备忘录与状态可查、
        跨用户隔离；落在 JudgmentForge HTTP API 缝上，默认 FakeLLM 不花真模型费用。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app（/auth/*、/projects/*、/runs*）。
"""

from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from judgment_forge.app import create_app
from judgment_forge.settings import Settings


def _client() -> TestClient:
    # 强制 fake provider，避免测试误连真模型。
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
        json={"name": "研判仓", "description": "minimal run"},
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
    assert upload.json()["status"] == "ready"
    return upload.json()["id"]


def test_owner_can_start_run_complete_and_fetch_memo_with_fake_llm():
    """
    所有者带问题启动 run（可开 checklist 开关，但 web 仍关闭）；
    FakeLLM 下跑完 Planner→Researcher→Critic→Writer（+ 可选 checklist 闸）；
    状态可查；备忘录含必填四段，材料主张带锚点或标明推断/未知。
    """
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    material_id = _upload_notes(
        client,
        headers,
        project_id,
        "Self-building on LangGraph gives auditability of agent steps.\n"
        "Managed platforms ship faster for small teams.\n",
    )

    started = client.post(
        f"/projects/{project_id}/runs",
        headers=headers,
        json={
            "question": "Should we self-build orchestration or use a managed agent?",
            "produce_checklist": True,
        },
    )
    assert started.status_code == 201
    run = started.json()
    run_id = run["id"]
    assert run["status"] == "waiting_for_human"
    assert run["produce_checklist"] is True
    assert run["web_enabled"] is False
    assert "question" in run

    # 工单 08：联网闸门默认暂停；本用例拒绝联网，走材料-only。
    decided = client.post(
        f"/projects/{project_id}/runs/{run_id}/hitl",
        headers=headers,
        json={"gate": "web", "decision": "deny"},
    )
    assert decided.status_code == 200
    # 工单 09：opt-in 时 Writer 后停在第二道清单闸；此处拒绝 → 仅备忘录。
    assert decided.json()["status"] == "waiting_for_human"
    assert decided.json()["pending_hitl"]["gate"] == "checklist"
    checklist_decided = client.post(
        f"/projects/{project_id}/runs/{run_id}/hitl",
        headers=headers,
        json={"gate": "checklist", "decision": "deny"},
    )
    assert checklist_decided.status_code == 200
    assert checklist_decided.json()["status"] == "completed"
    assert checklist_decided.json()["web_enabled"] is False

    status_resp = client.get(
        f"/projects/{project_id}/runs/{run_id}",
        headers=headers,
    )
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["status"] == "completed"
    assert status_body["id"] == run_id
    assert status_body["status"] in {
        "queued",
        "running",
        "waiting_for_human",
        "completed",
        "failed",
        "cancelled",
    }

    memo_resp = client.get(
        f"/projects/{project_id}/runs/{run_id}/memo",
        headers=headers,
    )
    assert memo_resp.status_code == 200
    memo = memo_resp.json()
    for key in ("conclusion", "options", "risks_unknowns", "next_steps"):
        assert key in memo
        assert isinstance(memo[key], str)
        assert memo[key].strip() != ""
    assert not memo.get("checklist")

    claims = memo["claims"]
    assert isinstance(claims, list)
    assert len(claims) >= 1
    for claim in claims:
        assert claim["presented_as"] in {"fact", "inference"}
        if claim["presented_as"] == "fact":
            assert len(claim["anchors"]) >= 1
            for anchor in claim["anchors"]:
                assert "material_id" in anchor
                assert "location_hint" in anchor
                assert anchor["material_id"] == material_id
        else:
            # 推断/未知：允许无锚点，但不得伪装成事实
            assert claim["presented_as"] == "inference"


def test_cross_user_cannot_read_another_users_run_or_memo():
    """跨用户不可读他人 run / 备忘录（与真缺失同形 404）。"""
    client = _client()
    owner = _register_and_login(client)
    other = _register_and_login(client)
    project_id = _create_project(client, owner)
    _upload_notes(
        client,
        owner,
        project_id,
        "LangGraph orchestration is inspectable via first-party traces.\n",
    )

    started = client.post(
        f"/projects/{project_id}/runs",
        headers=owner,
        json={"question": "Is first-party trace valuable?"},
    )
    assert started.status_code == 201
    run_id = started.json()["id"]
    assert started.json()["status"] == "waiting_for_human"
    assert (
        client.post(
            f"/projects/{project_id}/runs/{run_id}/hitl",
            headers=owner,
            json={"gate": "web", "decision": "deny"},
        ).json()["status"]
        == "completed"
    )

    assert (
        client.get(
            f"/projects/{project_id}/runs/{run_id}",
            headers=other,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/projects/{project_id}/runs/{run_id}/memo",
            headers=other,
        ).status_code
        == 404
    )
    # 他人也不能在别人的项目上开跑
    assert (
        client.post(
            f"/projects/{project_id}/runs",
            headers=other,
            json={"question": "hijack?"},
        ).status_code
        == 404
    )
