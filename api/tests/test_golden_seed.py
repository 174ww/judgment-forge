"""
为何存在：验收金路径种子包（工单 13）——材料可枚举、可经 HTTP 上传并检索；
        缝仍是 JudgmentForge HTTP API，不测 CLI 进程本身。
谁调用：pytest。
调用谁：judgment_forge.seed.pack / apply + FastAPI TestClient → app。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from judgment_forge.app import create_app
from judgment_forge.seed.apply import apply_golden_seed, register_or_login
from judgment_forge.seed.pack import (
    GOLDEN_PROJECT_DESCRIPTION,
    GOLDEN_PROJECT_NAME,
    GOLDEN_QUESTION,
    list_seed_material_files,
    resolve_pack_dir,
)


def _client() -> TestClient:
    return TestClient(create_app())


def _unique_email() -> str:
    return f"seed-{uuid.uuid4().hex}@example.com"

def test_seed_pack_lists_landscape_and_excerpts():
    """种子包须含 landscape 调研笔记与官方摘录，且金问题常量非空。"""
    pack = resolve_pack_dir()
    files = list_seed_material_files(pack)

    names = {path.name for path in files}
    assert "agent-dev-landscape.md" in names
    assert any(name.startswith("excerpt-") and name.endswith(".md") for name in names)
    assert len(files) >= 3

    landscape = next(p for p in files if p.name == "agent-dev-landscape.md")
    text = landscape.read_text(encoding="utf-8")
    assert "LangGraph" in text
    assert "百炼" in text or "orchestration" in text.lower()

    assert "LangGraph" in GOLDEN_QUESTION or "orchestration" in GOLDEN_QUESTION.lower()
    assert GOLDEN_PROJECT_NAME
    assert GOLDEN_PROJECT_DESCRIPTION


def test_seed_materials_upload_and_search_via_api():
    """apply_golden_seed 经 HTTP 播种后材料 ready，且检索可命中分层关键词。"""
    client = _client()
    email = _unique_email()
    headers = register_or_login(
        client, email=email, password="correct-horse-battery"
    )
    result = apply_golden_seed(client, headers=headers)

    assert result.project_id
    assert len(result.material_ids) >= 3
    assert "agent-dev-landscape.md" in result.filenames

    listed = client.get(
        f"/projects/{result.project_id}/materials", headers=headers
    )
    assert listed.status_code == 200
    assert all(item["status"] == "ready" for item in listed.json())

    search = client.get(
        f"/projects/{result.project_id}/materials/search",
        headers=headers,
        params={"q": "LangGraph orchestration"},
    )
    assert search.status_code == 200
    hits = search.json()
    assert len(hits) >= 1
    assert any("LangGraph" in hit.get("content", "") for hit in hits)


def test_register_or_login_is_idempotent_on_existing_email():
    """同一邮箱再次播种前应登录成功，而不是卡在 409。"""
    client = _client()
    email = _unique_email()
    password = "correct-horse-battery"
    first = register_or_login(client, email=email, password=password)
    second = register_or_login(client, email=email, password=password)
    assert "Authorization" in first and "Authorization" in second
