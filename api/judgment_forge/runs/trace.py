"""
为何存在：一等公民 Run Trace——把编排过程收成可检视、可持久化的有序事件，
        不依赖 LangSmith 等外部 vendor（可选对接留给日后）。
谁调用：runs.service（绑定缓冲、flush、读时间线）；runs.graph / nodes /
        provider.agent_chat（编排钩子里 emit）；routes 经 service 读模型服务 UI。
调用谁：仅标准库（contextvars / datetime / typing）——故意不碰 DB；落库由 repository 做。

事件谁发出：
  - 图节点进出：graph 包装钩子 → kind=node
  - 工具调用：Researcher 调 materials.search / web_search 时 → kind=tool
  - 模型补全：complete_for_agent → kind=llm（可带粗粒度 token/时延）
  - Critic 打回：critic 节点 → kind=critic_bounce
  - HITL / cancel：service 在写 hitl_events 时同步 emit → kind=hitl|cancelled

落在何处：进程内 TraceBuffer（ContextVar）→ invoke 段结束 flush 进
        judgment_runs.trace_events JSONB；API 按 seq 有序返回给时间线 UI。
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator

# 当前 invoke/resume 段绑定的缓冲；无绑定时 emit 为空操作（单测节点不强制有 sink）。
_current_buffer: ContextVar["TraceBuffer | None"] = ContextVar(
    "judgment_forge_trace_buffer", default=None
)


def utc_now_iso() -> str:
    """Trace / HITL 共用的 UTC ISO8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


class TraceBuffer:
    """
    单次 invoke/resume 段的内存事件缓冲。

    意图：图节点与工具不直写 DB；service 在段末（含 interrupt 停住前）一次性 append。
    seq 在 flush 时由仓储按已有长度续编，保证跨 HITL 段全局有序。
    """

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def emit(self, **fields: Any) -> None:
        """追加一条事件；自动补 at；调用方提供 kind 与业务字段。"""
        event = dict(fields)
        event.setdefault("at", utc_now_iso())
        self._events.append(event)

    def drain(self) -> list[dict[str, Any]]:
        """取出并清空缓冲（供 service flush）。"""
        out = self._events
        self._events = []
        return out

    @property
    def pending(self) -> list[dict[str, Any]]:
        """只读窥探（测试/调试）；生产路径用 drain。"""
        return list(self._events)


def emit_trace(**fields: Any) -> None:
    """
    编排钩子入口：若当前协程/线程已 bind TraceBuffer 则写入，否则静默跳过。

    意图：节点/工具可无条件调用，不必把 sink 参数钻透每一层工厂。
    """
    buf = _current_buffer.get()
    if buf is not None:
        buf.emit(**fields)


@contextmanager
def bind_trace_buffer(buffer: TraceBuffer | None = None) -> Iterator[TraceBuffer]:
    """
    绑定本段 TraceBuffer 到 ContextVar；退出时复位。

    service._invoke_or_resume 在 graph.invoke 外包一层，保证节点 emit 有着落。
    """
    buf = buffer if buffer is not None else TraceBuffer()
    token = _current_buffer.set(buf)
    try:
        yield buf
    finally:
        _current_buffer.reset(token)
