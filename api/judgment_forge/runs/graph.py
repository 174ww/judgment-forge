"""
为何存在：研判流水线的「架构课」——用 LangGraph 把节点、Critic 打回边与两道 HITL 闸门钉死。
        读本文件应能口述：谁先跑、联网闸与清单闸如何 interrupt/resume、状态怎么流转。

控制流（工单 08+09+10+11：web + optional checklist + cancel/resume + trace）：

  START → Planner → web_gate ──(interrupt: 等人批联网)──→ waiting_for_human（图外）
                         └──(resume approve/deny)──→ Researcher → Critic
                              Critic ──(bounce, 未超限)──→ Researcher
                                     └──(放行 / 超限降级)──→ Writer
                                                              │
                         produce_checklist=False ─────────────┼──→ checklist_gate（直接放行）→ END
                         produce_checklist=True ──────────────┘
                              checklist_gate ──(interrupt: 定稿清单)──→ waiting_for_human
                                              └──(approve 存清单 / deny 仅 memo)──→ END

  检查点身份：MemorySaver + thread_id=str(run_id)；resume 用 Command(resume=decision)
  从 interrupt 节点接续，非整图重跑。cancel ≠ deny：cancel 在图外标 cancelled、不 resume；
  deny 仍 resume 并继续材料-only / 无清单路径。

  Trace（工单 11）：本文件用 _traced_node 包装每个图节点，发出 kind=node 的进出/时延；
  工具与 critic_bounce 由 nodes 内 emit；HITL 由 service 写入。事件经 ContextVar
  TraceBuffer 缓冲，段末落 trace_events。

  - Planner：写 plan（子问题）
  - web_gate：langgraph.interrupt；resume 后写 web_enabled / web_hitl_decision
  - Researcher：读 web_enabled；仅 True 时调 WebSearchPort；写 evidence + claims
  - Critic：读 claims/evidence；调 CitationPolicy；写 ready_for_writer / bounce_count
  - Writer：写 memo；opt-in 时另写 checklist_draft（不定稿）
  - checklist_gate：第二道硬闸；opt-out 跳过 interrupt；批准才写 checklist
  - 故意无外部写入：图与 service 只落本地 memo JSONB，不创建 GitHub/Jira 工单
  - 持久化与 HITL/cancel/trace API 不在图内：runs.service 持 checkpointer，invoke/Command(resume=…)

谁调用：runs.service（compile 后 invoke / resume；cancel 不经本图）。
调用谁：langgraph（含 MemorySaver checkpointer）；runs.nodes；runs.trace.emit_trace；
        注入的 Provider / Materials / Web。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from judgment_forge.materials.service import MaterialService
from judgment_forge.provider.port import ChatProvider
from judgment_forge.runs.nodes import (
    make_checklist_gate_node,
    make_critic_node,
    make_planner_node,
    make_researcher_node,
    make_web_gate_node,
    make_writer_node,
)
from judgment_forge.runs.state import JudgmentState
from judgment_forge.runs.trace import emit_trace
from judgment_forge.web.port import WebSearchPort

RouteAfterCritic = Literal["researcher", "writer"]


def route_after_critic(state: JudgmentState) -> RouteAfterCritic:
    """
    Critic 之后的条件边：未放行则打回 Researcher，否则进 Writer。

    ready_for_writer 由 Critic 节点根据 CitationPolicy + 打回上限写入。
    """
    if state.get("ready_for_writer"):
        return "writer"
    return "researcher"


def _traced_node(
    name: str, fn: Callable[[JudgmentState], dict[str, Any]]
) -> Callable[[JudgmentState], dict[str, Any]]:
    """
    包装图节点：进出时 emit kind=node，并记录粗粒度 latency_ms。

    意图：编排钩子集中在 graph 层，业务节点不必自己记「我被调度了」。
    """

    def wrapped(state: JudgmentState) -> dict[str, Any]:
        emit_trace(kind="node", name=name, phase="start")
        started = time.perf_counter()
        try:
            return fn(state)
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            emit_trace(
                kind="node",
                name=name,
                phase="end",
                latency_ms=latency_ms,
            )

    return wrapped


def build_judgment_graph(
    provider: ChatProvider,
    materials: MaterialService,
    web_search: WebSearchPort,
    *,
    checkpointer: MemorySaver | None = None,
):
    """
    组装并 compile 研判图。

    checkpointer 必须提供，否则 interrupt 后无法 Command(resume=…) 续跑；
    service 传入共享的 MemorySaver，使同一 run_id（thread_id）可跨 HTTP 请求接续，
    而不是整图重跑。Writer 之后固定进入 checklist_gate：opt-out 在节点内短路，
    opt-in 才 interrupt。cancel 不经本图——由 service 直接把 DB 标为 cancelled。
    各节点经 _traced_node 包装，保证 Run Trace 能看到 agent/node 切换。
    """
    graph = StateGraph(JudgmentState)
    graph.add_node("planner", _traced_node("planner", make_planner_node(provider)))
    graph.add_node("web_gate", _traced_node("web_gate", make_web_gate_node()))
    graph.add_node(
        "researcher",
        _traced_node(
            "researcher",
            make_researcher_node(provider, materials, web_search),
        ),
    )
    graph.add_node("critic", _traced_node("critic", make_critic_node()))
    graph.add_node("writer", _traced_node("writer", make_writer_node(provider)))
    graph.add_node(
        "checklist_gate",
        _traced_node("checklist_gate", make_checklist_gate_node()),
    )

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "web_gate")
    graph.add_edge("web_gate", "researcher")
    graph.add_edge("researcher", "critic")
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "researcher": "researcher",
            "writer": "writer",
        },
    )
    graph.add_edge("writer", "checklist_gate")
    graph.add_edge("checklist_gate", END)
    saver = checkpointer if checkpointer is not None else MemorySaver()
    return graph.compile(checkpointer=saver)
