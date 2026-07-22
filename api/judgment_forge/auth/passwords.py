"""
为何存在：密码哈希与校验的唯一入口，保证库中永不落明文。
谁调用：auth.service（注册写哈希、登录验哈希）。
调用谁：bcrypt。
"""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """把明文密码变成可持久化的 bcrypt 哈希字符串。"""
    digest = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """比对明文与已存哈希；不匹配时返回 False（不抛错）。"""
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )
