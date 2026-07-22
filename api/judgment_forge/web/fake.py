"""
为何存在：确定性 FakeWeb——实现 WebSearchPort，供 HITL 闸门测试证明「批准前未调网」。
谁调用：create_app 默认注入；pytest 经 app.state.web_search 读 call_count。
调用谁：web.port（WebHit）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from judgment_forge.web.port import WebHit


class FakeWebSearch:
    """
    记录每次 search 调用；返回固定命中（含 URL + 检索时间）。

    意图：工单 08 验收缝——批准前 call_count 必须为 0；批准后 ≥1 且锚点可断言。
    """

    def __init__(
        self,
        *,
        url: str = "https://example.com/agent-orchestration",
        title: str = "Agent orchestration notes",
        snippet: str = (
            "Official docs: first-party traces and human gates beat opaque managed runs."
        ),
        retrieved_at: datetime | None = None,
    ) -> None:
        self._url = url
        self._title = title
        self._snippet = snippet
        # None → 每次 search 用「当下」时间，满足 URL+检索时间语义；测试可注入固定时刻。
        self._retrieved_at = retrieved_at
        self._calls: list[str] = []

    @property
    def call_count(self) -> int:
        """已被 search 调用的次数。"""
        return len(self._calls)

    @property
    def calls(self) -> list[str]:
        """查询字符串历史（调试用）。"""
        return list(self._calls)

    def search(self, query: str, *, limit: int = 3) -> list[WebHit]:
        """记录调用并返回最多 limit 条脚本化命中；retrieved_at 取本次调用时刻。"""
        self._calls.append(query)
        retrieved_at = (
            self._retrieved_at
            if self._retrieved_at is not None
            else datetime.now(timezone.utc)
        )
        hit = WebHit(
            url=self._url,
            title=self._title,
            snippet=self._snippet,
            retrieved_at=retrieved_at,
        )
        return [hit][: max(0, limit)]
