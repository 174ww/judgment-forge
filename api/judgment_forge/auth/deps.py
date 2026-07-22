"""
为何存在：认证「夹层」——把 HTTP Bearer 转成当前用户，挡在路由与领域服务之间。
谁调用：需要登录态的路由（Depends(get_current_user)）；auth.routes 的 /me、/logout，
以及 projects / materials / runs 等受保护资源。
调用谁：Request.app.state 上的 AuthService.resolve_user；不直接碰仓储。

夹层位置：路由处理函数 → get_current_user（本模块）→ AuthService → Repository。
匿名或废 token 在此返回 401，领域服务看不到「半登录」状态。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from judgment_forge.auth.service import AuthService, InvalidSessionError, PublicUser

_bearer = HTTPBearer(auto_error=False)


def get_auth_service(request: Request) -> AuthService:
    """从 app.state 取出共享的 AuthService（create_app 时注入）。"""
    return request.app.state.auth_service


def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> PublicUser:
    """
    受保护路由的统一入口：无/坏 token → 401；成功则把 PublicUser 注入路由。

    这是「中间件式依赖」：路由只声明需要当前用户，不自己解析 Authorization。
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    service = get_auth_service(request)
    try:
        return service.resolve_user(credentials.credentials)
    except InvalidSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
