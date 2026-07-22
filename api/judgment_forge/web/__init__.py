"""
为何存在：web 包对外导出——Fake 实现与端口类型，供 app 注入与测试 import。
谁调用：judgment_forge.app、tests.test_hitl_web_gate。
调用谁：web.fake / web.port。
"""

from judgment_forge.web.fake import FakeWebSearch
from judgment_forge.web.port import WebHit, WebSearchPort

__all__ = ["FakeWebSearch", "WebHit", "WebSearchPort"]
