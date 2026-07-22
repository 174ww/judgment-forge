"""
为何存在：研判工坊 FastAPI 进程的应用工厂——HTTP 主缝；测试与 uvicorn 都从 create_app() 进入。
谁调用：uvicorn（模块:app）、pytest 的 TestClient、以及后续 ASGI 宿主。
调用谁：health / auth / projects / materials / runs 路由、Settings、schema.ensure_schema、
        AuthService / ProjectService / MaterialService / RunService、
        provider.factory、web.FakeWebSearch（默认注入，可被测试经 app.state.web_search 窥探）；
        CORSMiddleware（工单 12：允许本机 Next 工作台跨域带 Authorization）。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from judgment_forge.auth.routes import router as auth_router
from judgment_forge.auth.service import AuthService
from judgment_forge.health import router as health_router
from judgment_forge.materials.routes import router as materials_router
from judgment_forge.materials.service import MaterialService
from judgment_forge.projects.routes import router as projects_router
from judgment_forge.projects.service import ProjectService
from judgment_forge.provider.factory import build_chat_provider
from judgment_forge.runs.routes import router as runs_router
from judgment_forge.runs.service import RunService
from judgment_forge.schema import ensure_schema
from judgment_forge.settings import Settings, get_settings
from judgment_forge.web.fake import FakeWebSearch

# 本地 Next 工作台默认端口；生产可再收紧。
_LOCAL_WEB_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    组装并返回已配置的 FastAPI 应用。

    启动时幂等建表，并把 Auth / Project / Material / Run 服务与 ChatProvider、WebSearch 放进 app.state。
    RunService 持有同一 chat_provider、material_service、web_search 与 MemorySaver，
    保证图内 Agent 与 HTTP HITL resume 同源。
    测试时可注入 settings；编排只依赖端口，不要在路由里 new 厂商客户端。
    CORS：允许本机 web 源带 Authorization，否则浏览器金路径无法直连 :8000。
    """
    resolved = settings or get_settings()
    ensure_schema(resolved)
    resolved.materials_dir.mkdir(parents=True, exist_ok=True)

    web_search = FakeWebSearch()

    app = FastAPI(title="judgment-forge", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_LOCAL_WEB_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = resolved
    app.state.auth_service = AuthService(resolved)
    app.state.project_service = ProjectService(resolved)
    app.state.material_service = MaterialService(resolved)
    app.state.chat_provider = build_chat_provider(resolved)
    app.state.web_search = web_search
    app.state.run_service = RunService(
        resolved,
        chat_provider=app.state.chat_provider,
        material_service=app.state.material_service,
        web_search=web_search,
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(materials_router)
    app.include_router(runs_router)
    return app


# ASGI 入口：`uvicorn judgment_forge.app:app`
app = create_app()
