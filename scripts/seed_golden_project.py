#!/usr/bin/env python3
"""
为何存在：本地/演示一键把金路径种子项目写入正在运行的 API（工单 13）。
谁调用：演示者或开发者在终端执行；不由 uvicorn 自动调用。
调用谁：httpx → JudgmentForge HTTP API；judgment_forge.seed.pack / apply。

用法（先起 Postgres + API）：
  cd api
  python ../scripts/seed_golden_project.py
  python ../scripts/seed_golden_project.py --email demo@example.com --password 'demo-pass-12'
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许从仓库根直接 python scripts/... 时找到 judgment_forge。
_API_ROOT = Path(__file__).resolve().parents[1] / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

import httpx

from judgment_forge.seed.apply import apply_golden_seed, register_or_login
from judgment_forge.seed.pack import GOLDEN_QUESTION, resolve_pack_dir


def main(argv: list[str] | None = None) -> int:
    """解析 CLI → 登录 → 播种 → 打印项目 id 与金问题。"""
    parser = argparse.ArgumentParser(
        description="播种金路径项目（landscape 调研笔记 + 官方短摘录）。",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="JudgmentForge API base URL",
    )
    parser.add_argument("--email", default="golden-demo@example.com")
    parser.add_argument("--password", default="golden-demo-pass")
    parser.add_argument(
        "--pack-dir",
        type=Path,
        default=None,
        help="Override fixtures/golden-seed path",
    )
    args = parser.parse_args(argv)

    pack = resolve_pack_dir(args.pack_dir)
    print(f"pack: {pack}")

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60.0) as client:
        headers = register_or_login(
            client, email=args.email, password=args.password
        )
        result = apply_golden_seed(
            client, headers=headers, pack_dir=args.pack_dir
        )

    print(f"project_id: {result.project_id}")
    print(f"materials ({len(result.filenames)}): {', '.join(result.filenames)}")
    print(f"golden_question: {GOLDEN_QUESTION}")
    print("Next: open the web workbench, open this project, start a run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
