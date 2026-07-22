"""
为何存在：项目用例编排（创建/列表/重命名/归档），与 HTTP 解耦。
谁调用：projects.routes。
调用谁：projects.repository；owner_id 来自认证夹层注入的当前用户。

所有权校验落点：服务层每个按 id 操作都把 current_user.id 传给仓储；
仓储 WHERE 过滤后若无行，本层抛 ProjectNotFoundError（对外统一 404，不泄露他人项目存在性）。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from judgment_forge.projects.repository import ProjectRepository, ProjectRow
from judgment_forge.settings import Settings


@dataclass(frozen=True)
class PublicProject:
    id: UUID
    name: str
    description: str
    archived: bool


class ProjectError(Exception):
    """项目领域错误基类；路由层映射为 HTTP 状态。"""


class ProjectNotFoundError(ProjectError):
    """
    项目对当前用户不可见或不存在。

    故意与「他人项目」同形：调用方只能得到 not-found，不能区分是否存在于别的租户。
    """


class ProjectService:
    """把所有者身份与仓储串成可测用例；不感知 FastAPI Request。"""

    def __init__(self, settings: Settings) -> None:
        self._repo = ProjectRepository(settings)

    def create(
        self, owner_id: UUID, name: str, description: str
    ) -> PublicProject:
        """为当前用户创建项目；owner_id 必须来自已认证会话。"""
        row = self._repo.create(
            project_id=uuid4(),
            owner_id=owner_id,
            name=name,
            description=description,
        )
        return _to_public(row)

    def list_for_owner(self, owner_id: UUID) -> list[PublicProject]:
        """只返回该用户自己的项目列表。"""
        return [_to_public(row) for row in self._repo.list_by_owner(owner_id)]

    def get_for_owner(self, owner_id: UUID, project_id: UUID) -> PublicProject:
        """读取单个项目；非所有者 → ProjectNotFoundError。"""
        row = self._repo.get_for_owner(project_id, owner_id)
        if row is None:
            raise ProjectNotFoundError(str(project_id))
        return _to_public(row)

    def rename(
        self, owner_id: UUID, project_id: UUID, name: str
    ) -> PublicProject:
        """所有者重命名；非所有者 → ProjectNotFoundError。"""
        row = self._repo.update_name_for_owner(project_id, owner_id, name)
        if row is None:
            raise ProjectNotFoundError(str(project_id))
        return _to_public(row)

    def archive(self, owner_id: UUID, project_id: UUID) -> PublicProject:
        """所有者归档；非所有者 → ProjectNotFoundError。"""
        row = self._repo.archive_for_owner(project_id, owner_id)
        if row is None:
            raise ProjectNotFoundError(str(project_id))
        return _to_public(row)


def _to_public(row: ProjectRow) -> PublicProject:
    """去掉 owner_id 等内部字段，只暴露 API 公开形状。"""
    return PublicProject(
        id=row.id,
        name=row.name,
        description=row.description,
        archived=row.archived,
    )
