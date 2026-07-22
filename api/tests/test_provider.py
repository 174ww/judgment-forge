"""
为何存在：验收模型 Provider 端口可替换（FakeLLM ↔ OpenAI 兼容适配器），
        且 Agent 调用点不随接线变化（工单 05）。
谁调用：pytest。
调用谁：judgment_forge.provider（端口、FakeLLM、OpenAICompatible、工厂）与
        agent_chat 调用点；真实 HTTP 用 httpx.MockTransport，不花真模型费用。
"""

from __future__ import annotations

import json

import httpx
import pytest

from judgment_forge.provider.agent_chat import complete_for_agent
from judgment_forge.provider.fake import FakeLLM
from judgment_forge.provider.factory import build_chat_provider
from judgment_forge.provider.openai_compat import OpenAICompatibleProvider
from judgment_forge.provider.port import ChatMessage
from judgment_forge.settings import Settings


def test_fake_llm_returns_scripted_replies_in_order():
    """FakeLLM 按脚本顺序返回，供确定性单测。"""
    fake = FakeLLM(scripted=["第一答", "第二答"])
    messages = [ChatMessage(role="user", content="hello")]

    first = fake.complete(messages)
    second = fake.complete(messages)

    assert first.content == "第一答"
    assert second.content == "第二答"
    assert first.model == "fake"


def test_agent_call_site_uses_port_not_vendor_client():
    """
    产品调用点只收 ChatProvider 端口：换 Fake / 真适配器无需改 complete_for_agent。
    """
    fake = FakeLLM(scripted=["来自假模型"])
    real_skeleton = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        default_model="demo-model",
        client=_mock_openai_client(reply="来自真适配器骨架"),
    )

    via_fake = complete_for_agent(
        fake,
        [ChatMessage(role="user", content="q")],
    )
    via_real = complete_for_agent(
        real_skeleton,
        [ChatMessage(role="user", content="q")],
    )

    assert via_fake == "来自假模型"
    assert via_real == "来自真适配器骨架"


def test_factory_wires_fake_vs_openai_compatible_from_settings():
    """配置驱动工厂：llm_provider=fake|openai_compatible，编排只拿端口实例。"""
    fake = build_chat_provider(Settings(llm_provider="fake"))
    assert isinstance(fake, FakeLLM)

    real = build_chat_provider(
        Settings(
            llm_provider="openai_compatible",
            llm_api_key="sk-test",
            llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            llm_model="qwen-plus",
        )
    )
    assert isinstance(real, OpenAICompatibleProvider)
    assert real.default_model == "qwen-plus"


def test_openai_compatible_posts_chat_completions_shape():
    """真实适配器骨架发出 OpenAI 兼容 /chat/completions 请求体。"""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "model": "qwen-plus",
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    provider = OpenAICompatibleProvider(
        api_key="sk-secret",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.complete(
        [
            ChatMessage(role="system", content="你是助手"),
            ChatMessage(role="user", content="你好"),
        ]
    )

    assert result.content == "ok"
    assert result.model == "qwen-plus"
    assert result.prompt_tokens == 3
    assert result.completion_tokens == 1
    assert captured["url"] == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    assert captured["authorization"] == "Bearer sk-secret"
    assert captured["body"] == {
        "model": "qwen-plus",
        "messages": [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"},
        ],
    }


def test_factory_rejects_unknown_provider_name():
    with pytest.raises(ValueError, match="unknown llm_provider"):
        build_chat_provider(Settings(llm_provider="assistants-api"))


def _mock_openai_client(*, reply: str) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": reply}}],
                "model": "demo-model",
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))
