"""
为何存在：OpenAI 兼容 chat/completions 的真适配器骨架（含 DashScope compatible-mode）。
        用 HTTP JSON，不引入 Assistants API / 厂商专有 Agent SDK。
谁调用：factory（llm_provider=openai_compatible）；测试可注入 MockTransport 的 httpx.Client。
调用谁：httpx；provider.port 的消息类型。
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from judgment_forge.provider.port import ChatCompletion, ChatMessage


class OpenAICompatibleProvider:
    """
    配置驱动的真实适配器：POST {base_url}/chat/completions。

    base_url 例：
      - https://api.openai.com/v1
      - https://dashscope.aliyuncs.com/compatible-mode/v1
    构造/注入责任在 factory（或测试显式 new）；本类不读环境变量。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        default_model: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        """若本实例拥有 httpx.Client，则关闭连接池。"""
        if self._owns_client:
            self._client.close()

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletion:
        """把端口消息映射为 OpenAI 兼容请求，解析 choices[0].message.content。"""
        chosen_model = model or self.default_model
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages
            ],
        }
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return ChatCompletion(
            content=content,
            model=data.get("model") or chosen_model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
