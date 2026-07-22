"""
为何存在：项目行的持久化细节，把 SQL 挡在领域服务之外。
谁调用：projects.service。
调用谁：judgment_forge.db.get_connection、Settings。

多租户边界（仓储层）：凡按 id 读写的方法都带 owner_id 过滤；
越权调用方拿不到行（返回 None / 影响 0 行），由服务层统一当成「不存在」。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from psycopg.rows import dict_row

from judgment_forge.db import get_connection
from judgment_forge.settings import Settings


@dataclass(frozen=True)
class ProjectRow:
    id: UUID
    owner_id: UUID
    name: str
    description: str
    archived: bool


def _project_from_row(row: dict) -> ProjectRow:
    """把 projects 查询行收成 ProjectRow。"""
    return ProjectRow(
        id=row["id"],
        owner_id=row["owner_id"],
        name=row["name"],
        description=row["description"],
        archived=row["archived"],
    )


class ProjectRepository:
    """围绕 projects 表的读写；每个方法自管短连接，且带所有者过滤。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(
        self,
        project_id: UUID,
        owner_id: UUID,
        name: str,
        description: str,
    ) -> ProjectRow:
        """插入属于 owner_id 的新项目；默认未归档。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO projects (id, owner_id, name, description)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, owner_id, name, description, archived
                    """,
                    (project_id, owner_id, name, description),
                )
                row = cur.fetchone()
            conn.commit()
        assert row is not None
        return _project_from_row(row)

    def list_by_owner(self, owner_id: UUID) -> list[ProjectRow]:
        """列出某用户拥有的全部项目（含已归档），按创建时间倒序。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, owner_id, name, description, archived
                    FROM projects
                    WHERE owner_id = %s
                    ORDER BY created_at DESC
                    """,
                    (owner_id,),
                )
                rows = cur.fetchall()
        return [_project_from_row(row) for row in rows]

    def get_for_owner(self, project_id: UUID, owner_id: UUID) -> ProjectRow | None:
        """
        按 id 取项目，但必须同时匹配 owner_id。

        所有权校验落点：SQL WHERE 同时约束 id 与 owner_id；
        他人项目 id 在此不可见（None），与「不存在」同形。
        """
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, owner_id, name, description, archived
                    FROM projects
                    WHERE id = %s AND owner_id = %s
                    """,
                    (project_id, owner_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return _project_from_row(row)

    def update_name_for_owner(
        self, project_id: UUID, owner_id: UUID, name: str
    ) -> ProjectRow | None:
        """重命名；WHERE 含 owner_id，越权则影响 0 行并返回 None。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE projects
                    SET name = %s
                    WHERE id = %s AND owner_id = %s
                    RETURNING id, owner_id, name, description, archived
                    """,
                    (name, project_id, owner_id),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return _project_from_row(row)

    def archive_for_owner(
        self, project_id: UUID, owner_id: UUID
    ) -> ProjectRow | None:
        """归档；WHERE 含 owner_id，越权则返回 None。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE projects
                    SET archived = TRUE
                    WHERE id = %s AND owner_id = %s
                    RETURNING id, owner_id, name, description, archived
                    """,
                    (project_id, owner_id),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return _project_from_row(row)
