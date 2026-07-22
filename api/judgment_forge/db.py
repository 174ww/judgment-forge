"""
为何存在：统一 Postgres 连接与可达性探测，供健康检查与业务仓储共用。
谁调用：judgment_forge.health、judgment_forge.schema、
        auth / projects / materials / runs 仓储。
调用谁：通过 Settings.database_url 使用 psycopg。
"""

from __future__ import annotations

import psycopg
from psycopg import Connection

from judgment_forge.settings import Settings


def get_connection(settings: Settings) -> Connection:
    """打开一条短连接；调用方负责 with/commit/close。"""
    return psycopg.connect(settings.database_url, connect_timeout=5)


def check_database(settings: Settings) -> bool:
    """
    对 Postgres 做一次轻量往返；成功返回 True。

    /health 用它区分「API 进程活着」与「数据面也能应答」。
    """
    try:
        with get_connection(settings) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
                return row is not None and row[0] == 1
    except psycopg.Error:
        return False
