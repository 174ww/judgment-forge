"""
为何存在：项目资源的 HTTP 表面（创建/列表/详情/重命名/归档），对外 API 缝的一部分。
谁调用：create_app 挂载本 router；TestClient / 前端调用这些路径。
调用谁：projects.service 做用例；经 auth.deps.get_current_user 取得所有者身份。

所有权校验落点：路由只把 current_user.id 交给 ProjectService；
跨用户访问在服务层变成 ProjectNotFoundError，本层统一映射为 404（与「真不存在」同形）。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from judgment_forge.auth.deps import get_current_user
from judgment_forge.auth.service import PublicUser
from judgment_forge.projects.service import (
    ProjectNotFoundError,
    ProjectService,
    PublicProject,
)

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class RenameProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str
    archived: bool


def get_project_service(request: Request) -> ProjectService:
    """从 app.state 取出共享的 ProjectService（create_app 时注入）。"""
    return request.app.state.project_service


def _to_response(project: PublicProject) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        archived=project.archived,
    )


def _http_not_found(exc: ProjectNotFoundError) -> HTTPException:
    """跨用户与真缺失统一映射为 404，避免泄露他人项目存在性。"""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="project not found",
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectResponse,
)
def create_project(
    body: CreateProjectRequest,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """已登录用户创建自己的项目。"""
    project = service.create(user.id, body.name, body.description)
    return _to_response(project)


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> list[ProjectResponse]:
    """列出当前用户拥有的项目（不含他人）。"""
    return [_to_response(p) for p in service.list_for_owner(user.id)]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """读取单个项目；非所有者得到 404。"""
    try:
        project = service.get_for_owner(user.id, project_id)
    except ProjectNotFoundError as exc:
        raise _http_not_found(exc) from exc
    return _to_response(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def rename_project(
    project_id: UUID,
    body: RenameProjectRequest,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """所有者重命名项目；非所有者 → 404。"""
    try:
        project = service.rename(user.id, project_id, body.name)
    except ProjectNotFoundError as exc:
        raise _http_not_found(exc) from exc
    return _to_response(project)


@router.post("/{project_id}/archive", response_model=ProjectResponse)
def archive_project(
    project_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """所有者归档项目；非所有者 → 404。"""
    try:
        project = service.archive(user.id, project_id)
    except ProjectNotFoundError as exc:
        raise _http_not_found(exc) from exc
    return _to_response(project)
