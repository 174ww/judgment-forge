"""
为何存在：materials / material_chunks 表的持久化细节，把 SQL 挡在领域服务之外。
谁调用：materials.service。
调用谁：judgment_forge.db.get_connection、Settings。

多租户边界：列表/删除/检索均带 project_id + owner_id；
越权拿不到行，由服务层统一当成「不存在」。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg.rows import dict_row

from judgment_forge.db import get_connection
from judgment_forge.materials.ingest import ParsedChunk
from judgment_forge.settings import Settings


@dataclass(frozen=True)
class MaterialRow:
    id: UUID
    project_id: UUID
    owner_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    status: str
    error_message: str | None


@dataclass(frozen=True)
class ChunkHit:
    """检索命中：块正文 + 文档 id + 位置提示（供引用锚点）。"""

    chunk_id: UUID
    material_id: UUID
    content: str
    location_hint: str
    rank: float


def _material_from_row(row: dict) -> MaterialRow:
    """把 materials 查询行收成 MaterialRow。"""
    return MaterialRow(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        storage_path=row["storage_path"],
        status=row["status"],
        error_message=row["error_message"],
    )


_MATERIAL_COLS = (
    "id, project_id, owner_id, filename, content_type, size_bytes, "
    "storage_path, status, error_message"
)


class MaterialRepository:
    """材料元数据与切块的读写；每个方法自管短连接，且带所有者过滤。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def insert_processing(
        self,
        material_id: UUID,
        project_id: UUID,
        owner_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
    ) -> MaterialRow:
        """插入 processing 状态的材料行（落盘之后、解析之前）。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO materials (
                        id, project_id, owner_id, filename, content_type,
                        size_bytes, storage_path, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'processing')
                    RETURNING {_MATERIAL_COLS}
                    """,
                    (
                        material_id,
                        project_id,
                        owner_id,
                        filename,
                        content_type,
                        size_bytes,
                        storage_path,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        assert row is not None
        return _material_from_row(row)

    def mark_ready_with_chunks(
        self,
        material_id: UUID,
        owner_id: UUID,
        project_id: UUID,
        chunks: list[ParsedChunk],
    ) -> MaterialRow | None:
        """
        写入切块并把材料标为 ready（同一事务）。

        chunk 行带 material_id + location_hint，供后续锚点引用。
        """
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                for index, chunk in enumerate(chunks):
                    cur.execute(
                        """
                        INSERT INTO material_chunks (
                            id, material_id, project_id, owner_id,
                            chunk_index, content, location_hint
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            uuid4(),
                            material_id,
                            project_id,
                            owner_id,
                            index,
                            chunk.content,
                            chunk.location_hint,
                        ),
                    )
                cur.execute(
                    f"""
                    UPDATE materials
                    SET status = 'ready', error_message = NULL
                    WHERE id = %s AND owner_id = %s
                    RETURNING {_MATERIAL_COLS}
                    """,
                    (material_id, owner_id),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return _material_from_row(row)

    def mark_failed(
        self, material_id: UUID, owner_id: UUID, error_message: str
    ) -> MaterialRow | None:
        """解析失败时标 failed，保留原文件供排查；无 chunks。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    UPDATE materials
                    SET status = 'failed', error_message = %s
                    WHERE id = %s AND owner_id = %s
                    RETURNING {_MATERIAL_COLS}
                    """,
                    (error_message, material_id, owner_id),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return _material_from_row(row)

    def list_for_owner(
        self, project_id: UUID, owner_id: UUID
    ) -> list[MaterialRow]:
        """列出某用户在某项目下的材料（含各状态），按创建时间倒序。"""
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    SELECT {_MATERIAL_COLS}
                    FROM materials
                    WHERE project_id = %s AND owner_id = %s
                    ORDER BY created_at DESC
                    """,
                    (project_id, owner_id),
                )
                rows = cur.fetchall()
        return [_material_from_row(row) for row in rows]

    def delete_for_owner(
        self, material_id: UUID, project_id: UUID, owner_id: UUID
    ) -> MaterialRow | None:
        """
        删除材料行；chunks 经 ON DELETE CASCADE 一并消失，检索即不可见。

        返回被删行（含 storage_path）以便服务层清磁盘。
        """
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    DELETE FROM materials
                    WHERE id = %s AND project_id = %s AND owner_id = %s
                    RETURNING {_MATERIAL_COLS}
                    """,
                    (material_id, project_id, owner_id),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return _material_from_row(row)

    def search_chunks(
        self,
        project_id: UUID,
        owner_id: UUID,
        query: str,
        limit: int = 20,
    ) -> list[ChunkHit]:
        """
        在所有者项目内对 ready 材料的 chunks 做全文检索。

        只命中仍存在的材料（删除后无行）；附带 material_id + location_hint。
        """
        with get_connection(self._settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        c.id AS chunk_id,
                        c.material_id,
                        c.content,
                        c.location_hint,
                        ts_rank(c.tsv, plainto_tsquery('simple', %s)) AS rank
                    FROM material_chunks c
                    INNER JOIN materials m ON m.id = c.material_id
                    WHERE c.project_id = %s
                      AND c.owner_id = %s
                      AND m.status = 'ready'
                      AND c.tsv @@ plainto_tsquery('simple', %s)
                    ORDER BY rank DESC
                    LIMIT %s
                    """,
                    (query, project_id, owner_id, query, limit),
                )
                rows = cur.fetchall()
        return [
            ChunkHit(
                chunk_id=row["chunk_id"],
                material_id=row["material_id"],
                content=row["content"],
                location_hint=row["location_hint"],
                rank=float(row["rank"]),
            )
            for row in rows
        ]
