"""
为何存在：确定性 FakeLLM——实现 ChatProvider，供单测/API 缝测不花真模型费用。
谁调用：factory（llm_provider=fake）、pytest、后续研判 run 的 Fake 接线。
调用谁：provider.port（ChatMessage / ChatCompletion）。
"""

from __future__ import annotations

from collections.abc import Sequence

from judgment_forge.provider.port import ChatCompletion, ChatMessage


class FakeLLM:
    """
    按 scripted 列表依次返回助手内容；耗尽后重复最后一条（或固定兜底）。

    意图：让 Agent 调用点在测试里可预测，且与真适配器共用同一 complete() 形状。
    """

    def __init__(
        self,
        scripted: Sequence[str] | None = None,
        *,
        model_name: str = "fake",
    ) -> None:
        self._scripted = list(scripted) if scripted is not None else ["fake-reply"]
        self._index = 0
        self._model_name = model_name

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletion:
        """弹出下一条脚本回复；并给出粗粒度 token 估计供 Run Trace。"""
        prompt_chars = sum(len(m.content) for m in messages)
        if not self._scripted:
            text = "fake-reply"
        elif self._index < len(self._scripted):
            text = self._scripted[self._index]
            self._index += 1
        else:
            text = self._scripted[-1]
        # 粗估：约 4 字符 ≈ 1 token；可测即可，不追求与真模型一致。
        return ChatCompletion(
            content=text,
            model=model or self._model_name,
            prompt_tokens=max(1, prompt_chars // 4),
            completion_tokens=max(1, len(text) // 4),
        )
