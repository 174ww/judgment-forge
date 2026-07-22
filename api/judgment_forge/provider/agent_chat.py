"""
为何存在：Agent/编排侧的稳定调用点——只依赖 ChatProvider 端口，不 import 厂商 SDK。
谁调用：runs.nodes（Planner / Researcher / Writer）；测试证明换接线不改调用点。
调用谁：传入的 ChatProvider.complete()；runs.trace.emit_trace（粗粒度 llm 用量/时延）。
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from judgment_forge.provider.port import ChatMessage, ChatProvider
from judgment_forge.runs.trace import emit_trace


def complete_for_agent(
    provider: ChatProvider,
    messages: Sequence[ChatMessage],
    *,
    model: str | None = None,
) -> str:
    """
    产品代码应经此（或同等只收端口的封装）调模型。

    返回助手文本；换 FakeLLM / OpenAICompatibleProvider 时本函数签名不变。
    副作用：向当前 TraceBuffer 写 kind=llm（可含 prompt/completion tokens 与 latency_ms）。
    """
    started = time.perf_counter()
    result = provider.complete(messages, model=model)
    latency_ms = int((time.perf_counter() - started) * 1000)
    emit_trace(
        kind="llm",
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=latency_ms,
    )
    return result.content
