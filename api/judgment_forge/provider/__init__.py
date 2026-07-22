"""
为何存在：模型访问的端口-适配器层——产品/编排只依赖 ChatProvider 端口，
        真厂商 HTTP 与 FakeLLM 都实现同一端口，避免绑死某一 SDK。
谁调用：研判图节点经 agent_chat / RunService 注入的端口、本包 agent_chat、
        create_app 经 factory 注入；测试直接构造 Fake/适配器。
调用谁：port（协议与消息类型）、fake、openai_compat、factory、settings。
"""

from judgment_forge.provider.agent_chat import complete_for_agent
from judgment_forge.provider.fake import FakeLLM
from judgment_forge.provider.factory import build_chat_provider
from judgment_forge.provider.openai_compat import OpenAICompatibleProvider
from judgment_forge.provider.port import ChatCompletion, ChatMessage, ChatProvider

__all__ = [
    "ChatCompletion",
    "ChatMessage",
    "ChatProvider",
    "FakeLLM",
    "OpenAICompatibleProvider",
    "build_chat_provider",
    "complete_for_agent",
]
