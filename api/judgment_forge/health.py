"""
为何存在：研判工坊 API 的 HTTP 健康检查缝——工单 01 验收入口（无需登录）。
谁调用：create_app 里注册路由；测试里的 TestClient。
调用谁：judgment_forge.db.check_database，以及 app.state 上的 Settings。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from judgment_forge.db import check_database
from judgment_forge.settings import Settings

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    """
    一次返回 API 存活与 Postgres 是否可达。

    仅当两侧都健康时 status 为 "ok"；否则为 "degraded"，
    便于区分「进程挂了」和「库连不上」。
    """
    settings: Settings = request.app.state.settings
    database_ok = check_database(settings)
    return {
        "status": "ok" if database_ok else "degraded",
        "api": "ok",
        "database": "ok" if database_ok else "unavailable",
    }
