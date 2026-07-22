"""
为何存在：验收 JudgmentForge HTTP 主缝的 /health 能报告 API + Postgres 可达性（工单 01）；
        并确认本机 Web 源的 CORS 头（工单 12 金路径浏览器直连）。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app（GET /health）。
"""

from fastapi.testclient import TestClient

from judgment_forge.app import create_app


def test_health_reports_api_and_database_ok():
    """快乐路径：Postgres 能应答时整栈健康。"""
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "api": "ok",
        "database": "ok",
    }


def test_cors_allows_local_web_origin():
    """浏览器从 localhost:3000 访问时响应带 CORS 允许源。"""
    client = TestClient(create_app())
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
