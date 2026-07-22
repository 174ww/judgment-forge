"""
为何存在：材料原文件的本地对象存储适配（v1 文件系统），把字节落盘与路径拼装挡在业务外。
谁调用：materials.service（上传写入、删除清理）。
调用谁：Settings.materials_dir；标准库 pathlib / os。
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from judgment_forge.settings import Settings


class MaterialStorage:
    """按 project_id/material_id 组织文件；不感知解析或切块。"""

    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.materials_dir)

    def save(
        self,
        project_id: UUID,
        material_id: UUID,
        filename: str,
        data: bytes,
    ) -> str:
        """
        写入原文件并返回相对 storage_path（入库用）。

        路径形如 {project_id}/{material_id}/{filename}，相对 materials_dir。
        """
        safe_name = Path(filename).name or "upload.bin"
        relative = Path(str(project_id)) / str(material_id) / safe_name
        absolute = self._root / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(data)
        return relative.as_posix()

    def delete(self, storage_path: str) -> None:
        """删除原文件；目录若空则尽量清理，忽略已不存在的路径。"""
        absolute = self._root / storage_path
        try:
            absolute.unlink(missing_ok=True)
        except OSError:
            return
        parent = absolute.parent
        for _ in range(2):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
