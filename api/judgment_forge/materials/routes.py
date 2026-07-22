"""
为何存在：材料资源的 HTTP 表面（上传/列表/删除/检索），对外 API 缝的一部分。
谁调用：create_app 挂载本 router；TestClient / 前端调用这些路径。
调用谁：materials.service；经 auth.deps.get_current_user 取得所有者身份。

所有权校验落点：路由只把 current_user.id 交给 MaterialService；
跨用户访问在服务层变成 NotFound，本层统一映射为 404。
检索端点供验收与调试；业务上 Researcher 更应直接调 MaterialService.search。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from judgment_forge.auth.deps import get_current_user
from judgment_forge.auth.service import PublicUser
from judgment_forge.materials.service import (
    InvalidUploadError,
    MaterialNotFoundError,
    MaterialService,
    ProjectNotFoundForMaterialError,
    PublicChunkHit,
    PublicMaterial,
)

router = APIRouter(prefix="/projects/{project_id}/materials", tags=["materials"])


class MaterialResponse(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    error_message: str | None = None


class ChunkHitResponse(BaseModel):
    material_id: UUID
    chunk_id: UUID
    content: str
    location_hint: str
    rank: float = Field(ge=0)


def get_material_service(request: Request) -> MaterialService:
    """从 app.state 取出共享的 MaterialService（create_app 时注入）。"""
    return request.app.state.material_service


def _to_material_response(material: PublicMaterial) -> MaterialResponse:
    return MaterialResponse(
        id=material.id,
        filename=material.filename,
        content_type=material.content_type,
        size_bytes=material.size_bytes,
        status=material.status,
        error_message=material.error_message,
    )


def _to_hit_response(hit: PublicChunkHit) -> ChunkHitResponse:
    return ChunkHitResponse(
        material_id=hit.material_id,
        chunk_id=hit.chunk_id,
        content=hit.content,
        location_hint=hit.location_hint,
        rank=hit.rank,
    )


def _http_project_or_material_not_found(
    exc: ProjectNotFoundForMaterialError | MaterialNotFoundError,
) -> HTTPException:
    """跨用户与真缺失统一 404，避免泄露他人资源存在性。"""
    detail = (
        "project not found"
        if isinstance(exc, ProjectNotFoundForMaterialError)
        else "material not found"
    )
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MaterialResponse)
async def upload_material(
    project_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[MaterialService, Depends(get_material_service)],
    file: UploadFile = File(...),
) -> MaterialResponse:
    """所有者上传 PDF/Markdown/纯文本；同步入库后返回最终 status。"""
    data = await file.read()
    filename = file.filename or "upload.bin"
    content_type = file.content_type or "application/octet-stream"
    try:
        material = service.upload(
            user.id, project_id, filename, content_type, data
        )
    except ProjectNotFoundForMaterialError as exc:
        raise _http_project_or_material_not_found(exc) from exc
    except InvalidUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _to_material_response(material)


@router.get("", response_model=list[MaterialResponse])
def list_materials(
    project_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[MaterialService, Depends(get_material_service)],
) -> list[MaterialResponse]:
    """列出项目材料及 processing/ready/failed 状态。"""
    try:
        materials = service.list_for_owner(user.id, project_id)
    except ProjectNotFoundForMaterialError as exc:
        raise _http_project_or_material_not_found(exc) from exc
    return [_to_material_response(m) for m in materials]


@router.get("/search", response_model=list[ChunkHitResponse])
def search_materials(
    project_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[MaterialService, Depends(get_material_service)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
) -> list[ChunkHitResponse]:
    """
    项目内全文检索（验收缝 + 调试）。

    生产路径上 Researcher 应调 MaterialService.search；本路由保持 HTTP 可观测。
    """
    try:
        hits = service.search(user.id, project_id, q)
    except ProjectNotFoundForMaterialError as exc:
        raise _http_project_or_material_not_found(exc) from exc
    return [_to_hit_response(h) for h in hits]


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    project_id: UUID,
    material_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[MaterialService, Depends(get_material_service)],
) -> None:
    """删除材料；删除后检索不再命中其 chunks。"""
    try:
        service.delete(user.id, project_id, material_id)
    except (ProjectNotFoundForMaterialError, MaterialNotFoundError) as exc:
        raise _http_project_or_material_not_found(exc) from exc
