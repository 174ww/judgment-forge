"""
为何存在：用户与会话的持久化细节，把 SQL 挡在领域服务之外。
谁调用：auth.service。
调用谁：judgment_forge.db.get_connection、Settings。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from judgment_forge.db import get_connection
from judgment_forge.settings import Settings


@dataclass(frozen=True)
class UserRow:
    id: UUID
    email: str
    password_hash: str


@dataclass(frozen=True)
class SessionRow:
    id: UUID
    user_id: UUID
    token_hash: str


def _user_from_row(row: dict) -> UserRow:
    """把 users 查询行收成 UserRow，避免多处手写字段映射。"""
    return UserRow(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
    )


class AuthRepository:
    """围绕 users / sessions 的读写；每个方法自管短连接。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_user(self, user_id: UUID, email: str, password_hash: str) -> UserRow:
        """插入新用户；email 唯一冲突时抛 DuplicateEmailError。"""
        try:
            with get_connection(self._settings) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        INSERT INTO users (id, email, password_hash)
                        VALUES (%s, %s, %s)
                        RETURNING id, email, password_hash
                        """,
                        (user_id, email, password_hash),
                    )
                    row = cur.fetchone()
                conn.commit()
        except psycopg.errors.UniqueViolation as exc:
            raise DuplicateEmailError(email) from exc

        assert row is not None
        return _user_from_row(row)

    def get_user_by_email(self, email: str) -> UserRow | None:
        """按规范化 email 查找用户；不存在返回 None。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, email, password_hash
                    FROM users
                    WHERE email = %s
                    """,
                    (email,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return _user_from_row(row)

    def get_user_by_id(self, user_id: UUID) -> UserRow | None:
        """按 id 取用户；供会话解析后组装当前用户。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, email, password_hash
                    FROM users
                    WHERE id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return _user_from_row(row)

    def create_session(
        self, session_id: UUID, user_id: UUID, token_hash: str
    ) -> SessionRow:
        """写入一条可撤销的会话（存 token 哈希，不存明文）。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO sessions (id, user_id, token_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, user_id, token_hash
                    """,
                    (session_id, user_id, token_hash),
                )
                row = cur.fetchone()
            conn.commit()
        assert row is not None
        return SessionRow(
            id=row["id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
        )

    def get_session_by_token_hash(self, token_hash: str) -> SessionRow | None:
        """用 token 哈希查找未删除的会话。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, user_id, token_hash
                    FROM sessions
                    WHERE token_hash = %s
                    """,
                    (token_hash,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return SessionRow(
            id=row["id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
        )

    def delete_session_by_token_hash(self, token_hash: str) -> bool:
        """删除会话以实现登出；返回是否删到了行。"""
        with get_connection(self._settings) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM sessions WHERE token_hash = %s",
                    (token_hash,),
                )
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted


class DuplicateEmailError(Exception):
    """邮箱已被占用；由仓储在唯一约束冲突时抛出。"""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"email already registered: {email}")
