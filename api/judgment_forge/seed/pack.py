"""
为何存在：描述金路径种子材料包的位置与清单（纯函数），供测试与 CLI 共用。
谁调用：judgment_forge.seed.apply、scripts/seed_golden_project、api/tests/test_golden_seed。
调用谁：pathlib（定位仓库根下 fixtures/golden-seed）。

设计意图：材料文件进 git，根目录调研笔记可继续 gitignore；产品演示以本包为准。
"""

from __future__ import annotations

from pathlib import Path

# 金问题：与 UI 默认题、spec 金路径一致，便于三分钟演示与评测清单对齐。
GOLDEN_QUESTION = (
    "Should an individual/small team self-build agent orchestration "
    "(LangGraph-class) or ship first on a managed agent (e.g. 百炼)?"
)

GOLDEN_PROJECT_NAME = "金路径：自建编排 vs 托管 Agent"
GOLDEN_PROJECT_DESCRIPTION = (
    "演示用种子项目：材料包含 Agent 开发生态调研笔记与短官方摘录。"
    f"默认金问题：{GOLDEN_QUESTION}"
)

# seed 包位于 api/judgment_forge/seed/ → parents[3] = 仓库根。
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PACK = _REPO_ROOT / "fixtures" / "golden-seed"
_MATERIALS_SUBDIR = "materials"


def resolve_pack_dir(pack_dir: Path | None = None) -> Path:
    """解析种子包根目录；默认指向仓库 fixtures/golden-seed。"""
    root = pack_dir if pack_dir is not None else _DEFAULT_PACK
    return root.resolve()


def materials_dir(pack_dir: Path | None = None) -> Path:
    """返回种子包内 materials/ 目录（可上传的 md/txt/pdf）。"""
    return resolve_pack_dir(pack_dir) / _MATERIALS_SUBDIR


def list_seed_material_files(pack_dir: Path | None = None) -> list[Path]:
    """
    列出可上传的种子材料，按文件名排序。
    仅纳入 .md / .txt / .pdf，忽略 README 等说明文件。
    """
    directory = materials_dir(pack_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"golden seed materials dir missing: {directory}")

    allowed = {".md", ".txt", ".pdf"}
    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in allowed
    ]
    return sorted(files, key=lambda p: p.name.lower())
