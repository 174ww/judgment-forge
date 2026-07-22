"""
为何存在：根据 Settings 构造 ChatProvider——「谁负责注入适配器」的唯一入口。
谁调用：create_app（写入 app.state.chat_provider）；测试直接调以断言接线。
调用谁：Settings；FakeLLM 或 OpenAICompatibleProvider。
"""

from __future__ import annotations

from judgment_forge.provider.fake import FakeLLM
from judgment_forge.provider.openai_compat import OpenAICompatibleProvider
from judgment_forge.provider.port import ChatProvider
from judgment_forge.settings import Settings


def build_chat_provider(settings: Settings) -> ChatProvider:
    """
    配置 → 端口实现。

    - fake：本地/CI 默认，确定性脚本回复
    - openai_compatible：OpenAI 或 DashScope 兼容模式（同一适配器，不同 base_url）
    编排拿到的永远是 ChatProvider，换厂商只改配置，不改 Agent 调用点。
    """
    name = settings.llm_provider.strip().lower()
    if name == "fake":
        return FakeLLM(scripted=["fake-reply"], model_name="fake")
    if name == "openai_compatible":
        return OpenAICompatibleProvider(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            default_model=settings.llm_model,
        )
    raise ValueError(
        f"unknown llm_provider={settings.llm_provider!r}; "
        "expected 'fake' or 'openai_compatible'"
    )
