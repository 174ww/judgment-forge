"""
为何存在：认证相关的 HTTP 表面（注册/登录/登出/当前用户），对外 API 缝的一部分。
谁调用：create_app 挂载本 router；TestClient / 前端调用这些路径。
调用谁：auth.service 做用例；受保护端点经 auth.deps.get_current_user 夹层取用户。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from judgment_forge.auth.deps import get_auth_service, get_current_user
from judgment_forge.auth.service import (
    AuthService,
    EmailTakenError,
    InvalidCredentialsError,
    PublicUser,
)

_bearer = HTTPBearer()

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    email: str


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserResponse


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
)
def register(
    body: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    """注册新账号；重复邮箱映射为 409。"""
    try:
        user = service.register(body.email, body.password)
    except EmailTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already registered",
        ) from exc
    return UserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """校验邮箱密码并返回会话 token。"""
    try:
        result = service.login(body.email, body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        ) from exc
    return TokenResponse(
        token=result.token,
        user=UserResponse(id=result.user.id, email=result.user.email),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """
    使当前 Bearer 会话失效。

    控制流：get_current_user（夹层）先拒匿名 → 再 AuthService.logout 删会话。
    user 用于强制鉴权；撤销按 credentials 中的 token 执行。
    """
    _ = user
    service.logout(credentials.credentials)

@router.get("/me", response_model=UserResponse)
def me(user: Annotated[PublicUser, Depends(get_current_user)]) -> UserResponse:
    """受保护探测端点：证明匿名被拒、有效会话可读到当前用户。"""
    return UserResponse(id=user.id, email=user.email)
