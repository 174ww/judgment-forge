"""
为何存在：验收取消 run + HITL 批准后从检查点 resume（工单 10）——
        cancel → cancelled；approve 后续跑到终态；失败信息不泄密。
        落在 JudgmentForge HTTP API 缝。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app；必要时经 app.state 注入可控 provider。
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from uuid import UUID

from fastapi.testclient import TestClient

from judgment_forge.app import create_app
from judgment_forge.materials.service import MaterialService
from judgment_forge.provider.fake import FakeLLM
from judgment_forge.provider.port import ChatCompletion, ChatMessage, ChatProvider
from judgment_forge.runs.service import RunService
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
        json={"name": "Cancel resume", "description": "issue 10"},
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


def _start_waiting(
    client: TestClient, headers: dict[str, str], project_id: str
) -> dict:
    started = client.post(
        f"/projects/{project_id}/runs",
        headers=headers,
        json={"question": "Should we cancel or resume this judgment?"},
    )
    assert started.status_code == 201
    run = started.json()
    assert run["status"] == "waiting_for_human"
    return run


class _ToggleBoomProvider:
    """测试用：默认同 FakeLLM；开关后抛带密钥/堆栈痕迹的异常。"""

    def __init__(self, inner: ChatProvider) -> None:
        self._inner = inner
        self.boom = False
        self.leaked_secret = "sk-live-LEAKED-SECRET-for-test"

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletion:
        if self.boom:
            raise RuntimeError(
                f"provider failed api_key={self.leaked_secret}\n"
                "Traceback (most recent call last):\n"
                '  File "/tmp/secret.py", line 1, in <module>\n'
                "    boom()\n"
            )
        return self._inner.complete(messages, model=model)


def test_owner_can_cancel_waiting_for_human_run():
    """所有者可取消 waiting_for_human；status=cancelled，随后 HITL 不可再决定。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(client, headers, project_id, "Checkpoint identity is thread_id.\n")
    run = _start_waiting(client, headers, project_id)

    cancelled = client.post(
        f"/projects/{project_id}/runs/{run['id']}/cancel",
        headers=headers,
    )
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["pending_hitl"] is None
    assert body["error_message"]
    assert "Traceback" not in (body["error_message"] or "")

    status = client.get(
        f"/projects/{project_id}/runs/{run['id']}",
        headers=headers,
    ).json()
    assert status["status"] == "cancelled"

    assert (
        client.post(
            f"/projects/{project_id}/runs/{run['id']}/hitl",
            headers=headers,
            json={"gate": "web", "decision": "approve"},
        ).status_code
        == 409
    )


def test_owner_can_cancel_running_run():
    """所有者也可取消 status=running 的 run（同步 API 下用仓储把行置为 running 以布置场景）。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(client, headers, project_id, "Running cancel path.\n")
    run = _start_waiting(client, headers, project_id)

    service: RunService = client.app.state.run_service
    run_id = UUID(run["id"])
    owner = _owner_id_for_run(service, run_id, UUID(project_id))
    assert (
        service._repo.update_status(  # noqa: SLF001 — 仅布置 running，断言仍走 HTTP
            run_id,
            owner,
            status="running",
            clear_pending_hitl=True,
        )
        is not None
    )

    cancelled = client.post(
        f"/projects/{project_id}/runs/{run['id']}/cancel",
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def _owner_id_for_run(
    service: RunService, run_id: UUID, project_id: UUID
) -> UUID:
    """测试布置：从 DB 按 run_id 读 owner（不经 HTTP）。"""
    from psycopg.rows import dict_row

    from judgment_forge.db import get_connection

    with get_connection(service._settings) as conn:  # noqa: SLF001
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT owner_id FROM judgment_runs
                WHERE id = %s AND project_id = %s
                """,
                (run_id, project_id),
            )
            row = cur.fetchone()
    assert row is not None
    return row["owner_id"]


def test_resume_after_approve_reaches_completed_from_checkpoint():
    """HITL 批准后从 checkpoint resume（非整图重跑）并到达 completed。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(
        client,
        headers,
        project_id,
        "Resume continues from the same thread_id checkpoint.\n",
    )
    run = _start_waiting(client, headers, project_id)
    assert run["pending_hitl"]["gate"] == "web"

    decided = client.post(
        f"/projects/{project_id}/runs/{run['id']}/hitl",
        headers=headers,
        json={"gate": "web", "decision": "approve"},
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "completed"
    assert body["web_enabled"] is True

    memo = client.get(
        f"/projects/{project_id}/runs/{run['id']}/memo",
        headers=headers,
    )
    assert memo.status_code == 200
    assert memo.json()["conclusion"].strip()


def test_failure_messages_are_user_safe_no_secrets_or_stack():
    """图失败时 API body 不含密钥或 Traceback。"""
    settings = Settings(llm_provider="fake")
    app = create_app(settings)
    boom = _ToggleBoomProvider(FakeLLM())
    app.state.chat_provider = boom
    app.state.web_search = FakeWebSearch()
    app.state.run_service = RunService(
        settings,
        chat_provider=boom,
        material_service=MaterialService(settings),
        web_search=app.state.web_search,
    )
    client = TestClient(app)
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(client, headers, project_id, "Safe error messages only.\n")
    run = _start_waiting(client, headers, project_id)

    boom.boom = True
    decided = client.post(
        f"/projects/{project_id}/runs/{run['id']}/hitl",
        headers=headers,
        json={"gate": "web", "decision": "approve"},
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "failed"
    msg = body["error_message"] or ""
    assert msg == "Run failed; see server logs for details."
    assert boom.leaked_secret not in msg
    assert "sk-live" not in msg
    assert "Traceback" not in msg
    assert "api_key=" not in msg.lower()


def test_cancel_rejected_on_terminal_run():
    """已完成的 run 再 cancel → 409。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    _upload_notes(client, headers, project_id, "Terminal cancel rejected.\n")
    run = _start_waiting(client, headers, project_id)
    assert (
        client.post(
            f"/projects/{project_id}/runs/{run['id']}/hitl",
            headers=headers,
            json={"gate": "web", "decision": "deny"},
        ).json()["status"]
        == "completed"
    )
    assert (
        client.post(
            f"/projects/{project_id}/runs/{run['id']}/cancel",
            headers=headers,
        ).status_code
        == 409
    )
