"""
为何存在：验收私有项目 CRUD 与跨用户隔离，落在 JudgmentForge HTTP API 缝上（工单 03）。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app（/auth/*、/projects/*）。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from judgment_forge.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _register_and_login(client: TestClient) -> dict[str, str]:
    """注册并登录，返回带 Bearer 的 Authorization headers。"""
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


def test_authenticated_user_can_create_project_with_name_and_description():
    """快乐路径：已登录用户可创建带名称与描述的项目。"""
    client = _client()
    headers = _register_and_login(client)

    created = client.post(
        "/projects",
        headers=headers,
        json={"name": "Agent 选型", "description": "自建 vs 托管"},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Agent 选型"
    assert body["description"] == "自建 vs 托管"
    assert "id" in body
    assert body["archived"] is False


def test_user_lists_only_their_own_projects():
    """列表只含当前用户的项目，不含他人创建的。"""
    client = _client()
    headers_a = _register_and_login(client)
    headers_b = _register_and_login(client)

    created_a = client.post(
        "/projects",
        headers=headers_a,
        json={"name": "A 的项目", "description": "仅 A"},
    )
    assert created_a.status_code == 201
    project_a_id = created_a.json()["id"]

    created_b = client.post(
        "/projects",
        headers=headers_b,
        json={"name": "B 的项目", "description": "仅 B"},
    )
    assert created_b.status_code == 201
    project_b_id = created_b.json()["id"]

    list_a = client.get("/projects", headers=headers_a)
    assert list_a.status_code == 200
    ids_a = {item["id"] for item in list_a.json()}
    assert project_a_id in ids_a
    assert project_b_id not in ids_a

    list_b = client.get("/projects", headers=headers_b)
    assert list_b.status_code == 200
    ids_b = {item["id"] for item in list_b.json()}
    assert project_b_id in ids_b
    assert project_a_id not in ids_b


def test_owner_can_rename_and_archive_project():
    """所有者可重命名并归档自己的项目。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = client.post(
        "/projects",
        headers=headers,
        json={"name": "旧名", "description": "desc"},
    ).json()["id"]

    renamed = client.patch(
        f"/projects/{project_id}",
        headers=headers,
        json={"name": "新名"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "新名"
    assert renamed.json()["archived"] is False

    archived = client.post(
        f"/projects/{project_id}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert archived.json()["name"] == "新名"

    fetched = client.get(f"/projects/{project_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "新名"
    assert fetched.json()["archived"] is True


def test_user_b_cannot_access_user_a_project_by_id():
    """
    跨用户隔离：用户 B 凭 A 的项目 id 读/改/归档应统一得到 404
    （与「不存在」同形，不泄露他人项目存在性）。
    """
    client = _client()
    headers_a = _register_and_login(client)
    headers_b = _register_and_login(client)
    project_a_id = client.post(
        "/projects",
        headers=headers_a,
        json={"name": "A 私有", "description": "secret"},
    ).json()["id"]

    get_b = client.get(f"/projects/{project_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    rename_b = client.patch(
        f"/projects/{project_a_id}",
        headers=headers_b,
        json={"name": "劫持改名"},
    )
    assert rename_b.status_code == 404

    archive_b = client.post(
        f"/projects/{project_a_id}/archive",
        headers=headers_b,
    )
    assert archive_b.status_code == 404

    still_a = client.get(f"/projects/{project_a_id}", headers=headers_a)
    assert still_a.status_code == 200
    assert still_a.json()["name"] == "A 私有"
    assert still_a.json()["archived"] is False


def test_anonymous_caller_cannot_use_project_routes():
    """未登录访问任一项目路由应 401（含按 id 读/改/归档）。"""
    client = _client()
    fake_id = str(uuid.uuid4())
    assert client.post(
        "/projects",
        json={"name": "匿名", "description": ""},
    ).status_code == 401
    assert client.get("/projects").status_code == 401
    assert client.get(f"/projects/{fake_id}").status_code == 401
    assert client.patch(
        f"/projects/{fake_id}",
        json={"name": "x"},
    ).status_code == 401
    assert client.post(f"/projects/{fake_id}/archive").status_code == 401
