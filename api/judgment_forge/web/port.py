"""
为何存在：联网/搜索工具的端口形状——与 Provider 一样可替换，便于 FakeWeb spy 验收。
谁调用：runs.nodes.Researcher（仅当 state.web_enabled 为真）；create_app 注入实现。
调用谁：无（typing / dataclasses）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class WebHit:
    """一次网页检索命中；引用策略要求对外暴露 url + retrieved_at。"""

    url: str
    title: str
    snippet: str
    retrieved_at: datetime


@runtime_checkable
class WebSearchPort(Protocol):
    """
    联网搜索端口。

    意图：Researcher 只依赖本协议；测试注入 FakeWebSearch 统计 call_count，
    证明 HITL 批准前绝不会进入 search()。
    """

    @property
    def call_count(self) -> int:
        """已被调用的次数（spy 侧信道）。"""
        ...

    def search(self, query: str, *, limit: int = 3) -> list[WebHit]:
        """按查询检索外部网页；实现方可打真实 HTTP，Fake 返回脚本化命中。"""
        ...
