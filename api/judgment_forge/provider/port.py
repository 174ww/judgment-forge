"""
为何存在：定义 chat completions 的端口（协议）与消息/结果值对象。
        这是六边形架构里的「内侧」：编排只认识本文件，不认识厂商。
谁调用：fake / openai_compat 实现方；agent_chat 与后续 Agent 节点；测试。
调用谁：无业务依赖（仅标准库 typing / dataclasses）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    """一轮对话中的单条消息；role 对齐 OpenAI 兼容 chat 字段。"""

    role: ChatRole
    content: str


@dataclass(frozen=True)
class ChatCompletion:
    """一次补全的规范化结果；token 字段可选，便于日后写入 Run Trace。"""

    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatProvider(Protocol):
    """
    模型提供方端口：Agent/编排只依赖 complete()，不依赖具体厂商客户端。

    实现方：FakeLLM（测）、OpenAICompatibleProvider（真骨架，含 DashScope 兼容模式）。
    """

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletion:
        """对 messages 做一轮 chat completion，返回助手文本与可选用量。"""
        ...
