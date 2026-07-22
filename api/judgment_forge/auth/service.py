"""
为何存在：认证用例编排（注册/登录/登出/解析当前用户），与 HTTP 解耦。
谁调用：auth.routes、auth.deps（经服务解析会话）。
调用谁：auth.repository、auth.passwords；生成会话 token。
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID, uuid4

from judgment_forge.auth.passwords import hash_password, verify_password
from judgment_forge.auth.repository import AuthRepository, DuplicateEmailError
from judgment_forge.settings import Settings


@dataclass(frozen=True)
class PublicUser:
    id: UUID
    email: str


@dataclass(frozen=True)
class LoginResult:
    token: str
    user: PublicUser


class AuthError(Exception):
    """认证领域错误的基类；路由层映射为 HTTP 状态。"""


class EmailTakenError(AuthError):
    """注册时邮箱冲突。"""


class InvalidCredentialsError(AuthError):
    """登录失败（邮箱不存在或密码不对）——对外同一错误，防枚举。"""


class InvalidSessionError(AuthError):
    """Bearer token 无效或已登出。"""


class AuthService:
    """把密码学与仓储串成可测用例；不感知 FastAPI Request。"""

    def __init__(self, settings: Settings) -> None:
        self._repo = AuthRepository(settings)

    def register(self, email: str, password: str) -> PublicUser:
        """创建账号并只返回公开字段；密码仅以哈希落库。"""
        normalized = _normalize_email(email)
        try:
            user = self._repo.create_user(
                user_id=uuid4(),
                email=normalized,
                password_hash=hash_password(password),
            )
        except DuplicateEmailError as exc:
            raise EmailTakenError(str(exc)) from exc
        return PublicUser(id=user.id, email=user.email)

    def login(self, email: str, password: str) -> LoginResult:
        """校验凭证并签发可撤销的会话 token（明文只返回一次）。"""
        normalized = _normalize_email(email)
        user = self._repo.get_user_by_email(normalized)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("invalid email or password")

        raw_token = secrets.token_urlsafe(32)
        self._repo.create_session(
            session_id=uuid4(),
            user_id=user.id,
            token_hash=_hash_token(raw_token),
        )
        return LoginResult(
            token=raw_token,
            user=PublicUser(id=user.id, email=user.email),
        )

    def logout(self, raw_token: str) -> None:
        """使会话失效；重复登出视为成功（幂等）。"""
        self._repo.delete_session_by_token_hash(_hash_token(raw_token))

    def resolve_user(self, raw_token: str) -> PublicUser:
        """把 Bearer token 解析成当前用户；无效则抛 InvalidSessionError。"""
        session = self._repo.get_session_by_token_hash(_hash_token(raw_token))
        if session is None:
            raise InvalidSessionError("invalid or expired session")
        user = self._repo.get_user_by_id(session.user_id)
        if user is None:
            raise InvalidSessionError("invalid or expired session")
        return PublicUser(id=user.id, email=user.email)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_token(raw_token: str) -> str:
    """会话表只存 token 的 SHA-256，泄露库也不直接等于可用凭证。"""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
