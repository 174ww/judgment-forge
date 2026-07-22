"""
为何存在：入库管线的「解析 → 切块」段——把原文件变成带 location_hint 的文本块。
谁调用：materials.service（上传后同步 ingest；状态 processing→ready|failed）。
调用谁：标准库 + pypdf（PDF）；不写库、不检索。

流水线位置：上传 → storage 落盘 → 本模块解析/切块 → repository 写入 chunks →（检索见 retrieval）。
后续 Researcher 不直接调用本模块，只消费已索引的 chunks。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader


@dataclass(frozen=True)
class ParsedChunk:
    """单一切块：正文 + 引用定位提示（page / section / paragraph）。"""

    content: str
    location_hint: str


class IngestError(Exception):
    """解析或切块失败；服务层据此把材料标为 failed。"""


def parse_and_chunk(
    filename: str,
    content_type: str,
    data: bytes,
) -> list[ParsedChunk]:
    """
    按类型解析全文并切块；空内容视为失败。

    - PDF：按页；location_hint = page:N
    - Markdown：按标题段；location_hint = section:…
    - 纯文本：按段落；location_hint = paragraph:N
    """
    kind = _detect_kind(filename, content_type)
    if kind == "pdf":
        pages = _parse_pdf(data)
        chunks = [
            ParsedChunk(content=text, location_hint=f"page:{page_no}")
            for page_no, text in pages
            if text.strip()
        ]
    elif kind == "markdown":
        chunks = _chunk_markdown(data.decode("utf-8", errors="replace"))
    else:
        chunks = _chunk_plain_text(data.decode("utf-8", errors="replace"))

    if not chunks:
        raise IngestError("no extractable text")
    return chunks


def _detect_kind(filename: str, content_type: str) -> str:
    """根据扩展名与 Content-Type 判定解析分支。"""
    lower = filename.lower()
    ctype = (content_type or "").split(";")[0].strip().lower()
    if lower.endswith(".pdf") or ctype == "application/pdf":
        return "pdf"
    if lower.endswith(".md") or ctype in {
        "text/markdown",
        "text/x-markdown",
    }:
        return "markdown"
    return "plain"


def _parse_pdf(data: bytes) -> list[tuple[int, str]]:
    """抽出 PDF 每页文本；损坏文件抛 IngestError。"""
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:  # pypdf 对坏文件抛多种异常
        raise IngestError("invalid pdf") from exc
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise IngestError("pdf page extract failed") from exc
        pages.append((index, text))
    return pages


def _chunk_markdown(text: str) -> list[ParsedChunk]:
    """按 ATx 标题切开；无标题则整篇一段。"""
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "preamble"
    current_body: list[str] = []
    heading = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    for line in lines:
        match = heading.match(line)
        if match:
            if current_body and any(part.strip() for part in current_body):
                sections.append((current_title, current_body))
            current_title = match.group(2).strip()
            current_body = []
        else:
            current_body.append(line)

    if current_body and any(part.strip() for part in current_body):
        sections.append((current_title, current_body))

    chunks: list[ParsedChunk] = []
    for title, body_lines in sections:
        content = "\n".join(body_lines).strip()
        if not content:
            continue
        safe_title = title.replace("\n", " ")[:80]
        chunks.append(
            ParsedChunk(content=content, location_hint=f"section:{safe_title}")
        )
    return chunks


def _chunk_plain_text(text: str) -> list[ParsedChunk]:
    """按空行分段；单段过长则再按字符窗切开。"""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[ParsedChunk] = []
    para_no = 0
    for paragraph in paragraphs:
        cleaned = paragraph.strip()
        if not cleaned:
            continue
        para_no += 1
        for piece_index, piece in enumerate(_window(cleaned, size=1200, overlap=100)):
            hint = f"paragraph:{para_no}"
            if piece_index > 0:
                hint = f"{hint}/part:{piece_index + 1}"
            chunks.append(ParsedChunk(content=piece, location_hint=hint))
    return chunks


def _window(text: str, size: int, overlap: int) -> list[str]:
    """定长滑动窗口；短文本原样返回。"""
    if len(text) <= size:
        return [text]
    step = max(size - overlap, 1)
    pieces: list[str] = []
    start = 0
    while start < len(text):
        pieces.append(text[start : start + size])
        start += step
    return pieces
