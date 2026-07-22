"""
为何存在：研判 run 包入口——编排、持久化与 HTTP 的聚合命名空间。
谁调用：judgment_forge.app 挂载 routes；测试经 HTTP 或直接 import graph/service。
调用谁：本包 routes / service / graph / nodes / repository / state / trace。

故意不在此 re-export router：避免 provider.agent_chat → runs.trace 时触发
routes→service→graph→nodes→agent_chat 的包初始化环。app 请直接
`from judgment_forge.runs.routes import router`。
"""

__all__: list[str] = []
