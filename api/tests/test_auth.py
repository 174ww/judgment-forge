"""
为何存在：验收认证主路径（注册/登录/登出/未授权）落在 JudgmentForge HTTP API 缝上（工单 02）。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app（/auth/*）。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from judgment_forge.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def test_user_can_register_with_email_and_password():
    """快乐路径：注册返回公开用户字段，不含密码。"""
    client = _client()
    email = _unique_email()
    password = "correct-horse-battery"

    register = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )

    assert register.status_code == 201
    body = register.json()
    assert body["email"] == email
    assert "id" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_duplicate_email_is_rejected_clearly():
    """同一邮箱再次注册应得到明确的冲突响应。"""
    client = _client()
    email = _unique_email()
    password = "correct-horse-battery"
    assert (
        client.post(
            "/auth/register",
            json={"email": email, "password": password},
        ).status_code
        == 201
    )

    duplicate = client.post(
        "/auth/register",
        json={"email": email, "password": "another-password-99"},
    )

    assert duplicate.status_code == 409
    assert "email" in duplicate.json()["detail"].lower()


def test_user_can_log_in_and_receive_usable_token():
    """登录返回可用 Bearer token，能访问受保护资源。"""
    client = _client()
    email = _unique_email()
    password = "correct-horse-battery"
    client.post("/auth/register", json={"email": email, "password": password})

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )

    assert login.status_code == 200
    token = login.json()["token"]
    assert isinstance(token, str) and len(token) > 20

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_user_can_log_out_and_token_stops_working():
    """登出后同一 token 再访问受保护路由应失败。"""
    client = _client()
    email = _unique_email()
    password = "correct-horse-battery"
    client.post("/auth/register", json={"email": email, "password": password})
    token = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout = client.post("/auth/logout", headers=headers)
    assert logout.status_code == 204

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 401


def test_protected_route_rejects_anonymous_caller():
    """未带凭证访问受保护路由应 401。"""
    client = _client()
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_password_is_not_stored_plaintext():
    """
    工单「at rest」验收：HTTP 缝看不到库内字段，故经仓储读回哈希做安全断言。

    仍先走 /auth/register 建账号；断言哈希≠明文且能校验原密码。
    """
    from judgment_forge.auth.passwords import verify_password
    from judgment_forge.auth.repository import AuthRepository
    from judgment_forge.settings import get_settings

    client = _client()
    email = _unique_email()
    password = "correct-horse-battery"
    client.post("/auth/register", json={"email": email, "password": password})

    user = AuthRepository(get_settings()).get_user_by_email(email)
    assert user is not None
    assert user.password_hash != password
    assert verify_password(password, user.password_hash)


def test_login_rejects_wrong_password():
    """错误密码不能换取 token。"""
    client = _client()
    email = _unique_email()
    client.post(
        "/auth/register",
        json={"email": email, "password": "correct-horse-battery"},
    )

    login = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password-xxx"},
    )
    assert login.status_code == 401
