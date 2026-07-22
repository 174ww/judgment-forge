"""
为何存在：材料检索的产品缝——把「按项目取证」与 HTTP/仓储细节隔开。
谁调用：materials.service.search（HTTP 验收路由经此间接调用）；
        Researcher 节点（runs.nodes）经 MaterialService.search 间接依赖本模块。
调用谁：materials.repository.search_chunks（Postgres 全文索引）。

与入库的关系：ingest 负责解析→切块；本模块只读 ready 且未删除的块，
并保留 material_id + location_hint，供 CitationPolicy / 决策备忘录锚点使用。
"""

from __future__ import annotations

from uuid import UUID

from judgment_forge.materials.repository import ChunkHit, MaterialRepository


def search_project_chunks(
    repo: MaterialRepository,
    *,
    project_id: UUID,
    owner_id: UUID,
    query: str,
    limit: int = 20,
) -> list[ChunkHit]:
    """
    在所有者项目内检索证据块。

    Researcher 路径：拿到 query → 本函数 → 带锚点的 ChunkHit 列表 → 写入研究笔记。
    空 query 由调用方过滤；本函数不做所有权以外的业务决策。
    """
    return repo.search_chunks(project_id, owner_id, query, limit=limit)
