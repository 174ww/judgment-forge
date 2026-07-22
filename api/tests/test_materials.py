"""
为何存在：验收材料上传/状态/删除/检索与跨用户隔离，落在 JudgmentForge HTTP API 缝上（工单 04）。
谁调用：pytest。
调用谁：FastAPI TestClient → judgment_forge.app（/auth/*、/projects/*、材料相关路径）。
"""

from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from judgment_forge.app import create_app
from judgment_forge.settings import Settings


def _client() -> TestClient:
    return TestClient(create_app())


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _register_and_login(client: TestClient) -> dict[str, str]:
    """注册并登录，返回带 Bearer 的 Authorization headers。"""
    email = _unique_email()
    password = "correct-horse-battery"
    assert (
        client.post(
            "/auth/register",
            json={"email": email, "password": password},
        ).status_code
        == 201
    )
    token = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project(client: TestClient, headers: dict[str, str]) -> str:
    """创建一个项目并返回其 id。"""
    created = client.post(
        "/projects",
        headers=headers,
        json={"name": "材料仓", "description": "upload pack"},
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_owner_can_upload_plain_text_material_and_see_ready_status():
    """所有者可上传纯文本；列表中该材料状态为 ready（含 processing/ready/failed 枚举）。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)

    upload = client.post(
        f"/projects/{project_id}/materials",
        headers=headers,
        files={
            "file": (
                "notes.txt",
                io.BytesIO(b"LangGraph is an orchestration runtime.\n"),
                "text/plain",
            )
        },
    )

    assert upload.status_code == 201
    body = upload.json()
    assert body["filename"] == "notes.txt"
    assert body["status"] in {"processing", "ready", "failed"}
    assert body["status"] == "ready"
    assert "id" in body

    listed = client.get(f"/projects/{project_id}/materials", headers=headers)
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == body["id"]
    assert items[0]["status"] == "ready"
    assert items[0]["filename"] == "notes.txt"


def test_disallowed_type_and_oversized_upload_are_rejected():
    """非法扩展名与超限体积在入口拒绝，不进入材料列表。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)

    bad_type = client.post(
        f"/projects/{project_id}/materials",
        headers=headers,
        files={
            "file": (
                "malware.exe",
                io.BytesIO(b"MZ-not-allowed"),
                "application/octet-stream",
            )
        },
    )
    assert bad_type.status_code == 400

    # 用小上限 settings 覆盖，避免分配真实 10MB+ 载荷。
    tiny = Settings(max_upload_bytes=64)
    tiny.materials_dir.mkdir(parents=True, exist_ok=True)
    small_client = TestClient(create_app(settings=tiny))
    small_headers = _register_and_login(small_client)
    small_project = _create_project(small_client, small_headers)
    oversized = small_client.post(
        f"/projects/{small_project}/materials",
        headers=small_headers,
        files={
            "file": (
                "big.txt",
                io.BytesIO(b"x" * 128),
                "text/plain",
            )
        },
    )
    assert oversized.status_code == 400

    listed = client.get(f"/projects/{project_id}/materials", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []


def test_ready_material_is_searchable_with_document_id_and_location_hint():
    """ready 材料可检索；命中块带 material_id 与 location_hint（锚点定位）。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)

    md = (
        "# Orchestration\n\n"
        "LangGraph provides durable multi-agent orchestration.\n\n"
        "## Managed platforms\n\n"
        "Bailian is a managed agent alternative.\n"
    ).encode("utf-8")
    upload = client.post(
        f"/projects/{project_id}/materials",
        headers=headers,
        files={"file": ("pack.md", io.BytesIO(md), "text/markdown")},
    )
    assert upload.status_code == 201
    material_id = upload.json()["id"]
    assert upload.json()["status"] == "ready"

    search = client.get(
        f"/projects/{project_id}/materials/search",
        headers=headers,
        params={"q": "LangGraph orchestration"},
    )
    assert search.status_code == 200
    hits = search.json()
    assert len(hits) >= 1
    assert hits[0]["material_id"] == material_id
    assert hits[0]["location_hint"].startswith("section:")
    assert "LangGraph" in hits[0]["content"]


def test_owner_can_delete_material_so_it_is_no_longer_retrieved():
    """删除后列表无该材料，检索也不再命中其内容。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    unique_token = f"UniqueToken{uuid.uuid4().hex}"
    upload = client.post(
        f"/projects/{project_id}/materials",
        headers=headers,
        files={
            "file": (
                "ephemeral.txt",
                io.BytesIO(f"Secret phrase {unique_token}\n".encode()),
                "text/plain",
            )
        },
    )
    assert upload.status_code == 201
    material_id = upload.json()["id"]

    before = client.get(
        f"/projects/{project_id}/materials/search",
        headers=headers,
        params={"q": unique_token},
    )
    assert before.status_code == 200
    assert any(h["material_id"] == material_id for h in before.json())

    deleted = client.delete(
        f"/projects/{project_id}/materials/{material_id}",
        headers=headers,
    )
    assert deleted.status_code == 204

    listed = client.get(f"/projects/{project_id}/materials", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []

    after = client.get(
        f"/projects/{project_id}/materials/search",
        headers=headers,
        params={"q": unique_token},
    )
    assert after.status_code == 200
    assert after.json() == []


def test_cross_user_cannot_access_another_users_materials():
    """跨用户隔离：B 不能列表/上传到/检索/删除 A 的项目材料（统一 404）。"""
    client = _client()
    headers_a = _register_and_login(client)
    headers_b = _register_and_login(client)
    project_a = _create_project(client, headers_a)

    upload_a = client.post(
        f"/projects/{project_a}/materials",
        headers=headers_a,
        files={
            "file": (
                "private.txt",
                io.BytesIO(b"Owner A private evidence about widgets.\n"),
                "text/plain",
            )
        },
    )
    assert upload_a.status_code == 201
    material_id = upload_a.json()["id"]

    list_b = client.get(f"/projects/{project_a}/materials", headers=headers_b)
    assert list_b.status_code == 404

    upload_b = client.post(
        f"/projects/{project_a}/materials",
        headers=headers_b,
        files={
            "file": (
                "intrude.txt",
                io.BytesIO(b"intrusion\n"),
                "text/plain",
            )
        },
    )
    assert upload_b.status_code == 404

    search_b = client.get(
        f"/projects/{project_a}/materials/search",
        headers=headers_b,
        params={"q": "widgets"},
    )
    assert search_b.status_code == 404

    delete_b = client.delete(
        f"/projects/{project_a}/materials/{material_id}",
        headers=headers_b,
    )
    assert delete_b.status_code == 404

    still_a = client.get(f"/projects/{project_a}/materials", headers=headers_a)
    assert still_a.status_code == 200
    assert len(still_a.json()) == 1
    assert still_a.json()[0]["id"] == material_id


def test_invalid_pdf_ends_as_failed_status():
    """损坏 PDF 仍创建材料行，但 status=failed（列表可见失败态）。"""
    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)

    upload = client.post(
        f"/projects/{project_id}/materials",
        headers=headers,
        files={
            "file": (
                "broken.pdf",
                io.BytesIO(b"%PDF-1.4 not-a-real-pdf"),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["status"] == "failed"
    assert body["error_message"]

    listed = client.get(f"/projects/{project_id}/materials", headers=headers)
    assert listed.json()[0]["status"] == "failed"


def test_valid_pdf_is_ready_and_searchable_with_page_location():
    """合法 PDF → ready；检索命中带 page: 位置提示。"""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    # 最小可抽取文本流，便于验收 page 定位（不依赖字体子集嵌入的复杂路径）。
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (LangGraph runtime PDF) Tj ET")
    stream_ref = writer._add_object(stream)
    page[NameObject("/Contents")] = stream_ref
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    client = _client()
    headers = _register_and_login(client)
    project_id = _create_project(client, headers)
    upload = client.post(
        f"/projects/{project_id}/materials",
        headers=headers,
        files={
            "file": ("evidence.pdf", io.BytesIO(pdf_bytes), "application/pdf")
        },
    )
    assert upload.status_code == 201
    assert upload.json()["status"] == "ready"
    material_id = upload.json()["id"]

    search = client.get(
        f"/projects/{project_id}/materials/search",
        headers=headers,
        params={"q": "LangGraph"},
    )
    assert search.status_code == 200
    hits = search.json()
    assert any(h["material_id"] == material_id for h in hits)
    assert any(h["location_hint"].startswith("page:") for h in hits)
