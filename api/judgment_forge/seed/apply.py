"""
为何存在：把金路径种子材料经 HTTP 写入某个用户的项目（演示/本地一键播种）。
谁调用：scripts/seed_golden_project.py；api/tests/test_golden_seed 直接调 apply_golden_seed。
调用谁：judgment_forge.seed.pack；httpx / TestClient 兼容的「client」表面
        （需实现 .post/.get，与 FastAPI TestClient 或 httpx.Client 同形）。

刻意走 HTTP 而非直连 MaterialService：与演示者「先起 API 再播种」心智一致，
也保证所有权/上传校验与真实金路径相同。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from judgment_forge.seed.pack import (
    GOLDEN_PROJECT_DESCRIPTION,
    GOLDEN_PROJECT_NAME,
    list_seed_material_files,
    resolve_pack_dir,
)


class HttpClient(Protocol):
    """最小 HTTP 客户端协议：TestClient 与 httpx.Client 均满足。"""

    def post(self, url: str, **kwargs: Any) -> Any: ...

    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class SeedResult:
    """一次播种的结果摘要，便于 CLI 打印与测试断言。"""

    project_id: str
    material_ids: tuple[str, ...]
    filenames: tuple[str, ...]


def _content_type_for(path: Path) -> str:
    """按扩展名给出上传 Content-Type；md 走 text/markdown。"""
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".pdf":
        return "application/pdf"
    return "text/plain"


def register_or_login(
    client: HttpClient,
    *,
    email: str,
    password: str,
) -> dict[str, str]:
    """
    注册演示账号；若邮箱已占用则改走登录。
    返回带 Bearer 的 Authorization headers。
    """
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    if reg.status_code not in (201, 409):
        raise RuntimeError(f"register failed: {reg.status_code} {reg.text}")

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    if login.status_code != 200:
        raise RuntimeError(f"login failed: {login.status_code} {login.text}")
    token = login.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def apply_golden_seed(
    client: HttpClient,
    *,
    headers: dict[str, str],
    pack_dir: Path | None = None,
    project_name: str = GOLDEN_PROJECT_NAME,
    project_description: str = GOLDEN_PROJECT_DESCRIPTION,
) -> SeedResult:
    """
    创建金路径项目并上传种子材料；假定调用方已登录。
    不启动 run——演示脚本要求面试官在 UI 上亲手点「启 run」。
    """
    pack = resolve_pack_dir(pack_dir)
    files = list_seed_material_files(pack)

    created = client.post(
        "/projects",
        headers=headers,
        json={"name": project_name, "description": project_description},
    )
    if created.status_code != 201:
        raise RuntimeError(
            f"create project failed: {created.status_code} {created.text}"
        )
    project_id = created.json()["id"]

    material_ids: list[str] = []
    filenames: list[str] = []
    for path in files:
        raw = path.read_bytes()
        resp = client.post(
            f"/projects/{project_id}/materials",
            headers=headers,
            files={"file": (path.name, raw, _content_type_for(path))},
        )
        if resp.status_code != 201:
            raise RuntimeError(
                f"upload {path.name} failed: {resp.status_code} {resp.text}"
            )
        body = resp.json()
        if body.get("status") != "ready":
            raise RuntimeError(
                f"upload {path.name} not ready: status={body.get('status')}"
            )
        material_ids.append(body["id"])
        filenames.append(body["filename"])

    return SeedResult(
        project_id=project_id,
        material_ids=tuple(material_ids),
        filenames=tuple(filenames),
    )
