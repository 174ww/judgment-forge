"""
为何存在：材料用例编排——上传→存储→解析→切块→索引，以及删除与项目内检索。
谁调用：materials.routes；Researcher（runs.nodes）调用 search() 取证，勿直连仓储。
调用谁：MaterialRepository、MaterialStorage、ingest.parse_and_chunk、ProjectRepository（所有权）。

流水线：
  1) 校验类型/大小 → 2) 确认项目归属 → 3) 落盘 → 4) 行 status=processing
  → 5) 解析切块 → 6) 写 chunks 并 ready（失败则 failed）
检索：search() 只查 ready 且未删除的块，块带 material_id + location_hint 供锚点。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from judgment_forge.materials.ingest import IngestError, parse_and_chunk
from judgment_forge.materials.repository import (
    ChunkHit,
    MaterialRepository,
    MaterialRow,
)
from judgment_forge.materials.retrieval import search_project_chunks
from judgment_forge.materials.storage import MaterialStorage
from judgment_forge.projects.repository import ProjectRepository
from judgment_forge.settings import Settings

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/markdown",
    "text/x-markdown",
    "text/plain",
    "application/octet-stream",  # 部分客户端上传 md/txt 时的兜底；仍靠扩展名把关
}


@dataclass(frozen=True)
class PublicMaterial:
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    error_message: str | None


@dataclass(frozen=True)
class PublicChunkHit:
    """检索结果的公开形状：文档 id + 位置提示 + 正文片段。"""

    material_id: UUID
    chunk_id: UUID
    content: str
    location_hint: str
    rank: float


class MaterialError(Exception):
    """材料领域错误基类；路由层映射为 HTTP 状态。"""


class MaterialNotFoundError(MaterialError):
    """材料对当前用户不可见或不存在（与跨用户同形）。"""


class ProjectNotFoundForMaterialError(MaterialError):
    """项目不可见时上传/列表/检索均失败，对外映射 404。"""


class InvalidUploadError(MaterialError):
    """类型或大小不合规；在落盘前拒绝。"""


class MaterialService:
    """把所有权、存储与入库管线串成可测用例；不感知 FastAPI Request。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._repo = MaterialRepository(settings)
        self._storage = MaterialStorage(settings)
        self._projects = ProjectRepository(settings)

    def upload(
        self,
        owner_id: UUID,
        project_id: UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> PublicMaterial:
        """
        所有者上传材料并同步走完入库管线。

        v1 在请求内完成 processing→ready|failed，故列表通常直接见到终态；
        processing 仍写入库，便于日后改异步索引时对外暴露中间态。
        非法类型/超限 → InvalidUploadError；非项目所有者 → ProjectNotFoundForMaterialError。
        """
        self._assert_allowed(filename, content_type, len(data))
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForMaterialError(str(project_id))

        material_id = uuid4()
        storage_path = self._storage.save(
            project_id, material_id, filename, data
        )
        row = self._repo.insert_processing(
            material_id=material_id,
            project_id=project_id,
            owner_id=owner_id,
            filename=PurePosixPath(filename).name or "upload.bin",
            content_type=content_type or "application/octet-stream",
            size_bytes=len(data),
            storage_path=storage_path,
        )
        return _to_public(self._finish_ingest(row, data))

    def list_for_owner(
        self, owner_id: UUID, project_id: UUID
    ) -> list[PublicMaterial]:
        """列出项目材料；非所有者 → ProjectNotFoundForMaterialError。"""
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForMaterialError(str(project_id))
        return [
            _to_public(row)
            for row in self._repo.list_for_owner(project_id, owner_id)
        ]

    def delete(
        self, owner_id: UUID, project_id: UUID, material_id: UUID
    ) -> None:
        """删除材料与磁盘文件；chunks 级联消失，检索不再命中。"""
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForMaterialError(str(project_id))
        deleted = self._repo.delete_for_owner(
            material_id, project_id, owner_id
        )
        if deleted is None:
            raise MaterialNotFoundError(str(material_id))
        self._storage.delete(deleted.storage_path)

    def search(
        self, owner_id: UUID, project_id: UUID, query: str, limit: int = 20
    ) -> list[PublicChunkHit]:
        """
        项目内检索 ready 材料块——产品缝给 Researcher 与 API 验收共用。

        命中项保留 document id（material_id）与 location_hint，供引用锚点。
        """
        if self._projects.get_for_owner(project_id, owner_id) is None:
            raise ProjectNotFoundForMaterialError(str(project_id))
        cleaned = query.strip()
        if not cleaned:
            return []
        # Researcher 将来也应走 search_project_chunks，而不是复制 SQL。
        hits = search_project_chunks(
            self._repo,
            project_id=project_id,
            owner_id=owner_id,
            query=cleaned,
            limit=limit,
        )
        return [_to_hit(hit) for hit in hits]

    def _finish_ingest(self, row: MaterialRow, data: bytes) -> MaterialRow:
        """processing → 解析切块 → ready；异常则 failed。"""
        try:
            chunks = parse_and_chunk(row.filename, row.content_type, data)
            ready = self._repo.mark_ready_with_chunks(
                row.id, row.owner_id, row.project_id, chunks
            )
            assert ready is not None
            return ready
        except IngestError as exc:
            failed = self._repo.mark_failed(row.id, row.owner_id, str(exc))
            assert failed is not None
            return failed

    def _assert_allowed(
        self, filename: str, content_type: str, size: int
    ) -> None:
        """入口闸门：扩展名白名单 + 大小上限（Content-Type 仅辅助）。"""
        if size > self._settings.max_upload_bytes:
            raise InvalidUploadError("file too large")
        if size == 0:
            raise InvalidUploadError("empty file")
        suffix = PurePosixPath(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise InvalidUploadError("disallowed file type")
        ctype = (content_type or "").split(";")[0].strip().lower()
        if ctype and ctype not in ALLOWED_CONTENT_TYPES:
            # 扩展名已过白名单时，仍允许常见误报类型（如 text/plain 的 .md）
            if not (
                suffix in {".md", ".txt"}
                and ctype.startswith("text/")
            ):
                raise InvalidUploadError("disallowed content type")


def _to_public(row: MaterialRow) -> PublicMaterial:
    """去掉 storage_path / owner_id 等内部字段，只暴露 API 公开形状。"""
    return PublicMaterial(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        status=row.status,
        error_message=row.error_message,
    )


def _to_hit(hit: ChunkHit) -> PublicChunkHit:
    """把仓储命中收成检索 API / Researcher 可用的公开形状。"""
    return PublicChunkHit(
        material_id=hit.material_id,
        chunk_id=hit.chunk_id,
        content=hit.content,
        location_hint=hit.location_hint,
        rank=hit.rank,
    )
