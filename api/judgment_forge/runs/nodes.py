"""
为何存在：业务 Agent 节点 + 两道 HITL 闸门——只改「本步写什么状态」，不决定边怎么连。
谁调用：runs.graph 把本模块函数注册为 LangGraph 节点（外层再包 _traced_node）。
调用谁：provider.agent_chat；materials.service.search；web.WebSearchPort（仅 web_enabled）；
        citation.policy.evaluate_claims；langgraph.types.interrupt（web_gate / checklist_gate）；
        runs.trace.emit_trace（工具调用与 Critic 打回事件）。

各节点何时跑（由 graph 调度，此处只描述写入意图）：
  Planner         —— 入口后第一步：把用户问题拆成子问题列表 → state.plan
  web_gate        —— Planner 之后：interrupt 等人批联网；resume 后写 web_enabled
  Researcher      —— web_gate 之后，或 Critic 打回之后：材料检索（+ 可选联网）→ evidence/claims
                     每次 search 发出 kind=tool
  Critic          —— Researcher 之后：CitationPolicy 裁决 → ready_for_writer / bounce
                     打回时发出 kind=critic_bounce
  Writer          —— Critic 放行后：组装备忘录四段 → memo；
                     若 produce_checklist：另写 checklist_draft（仍不定稿）
  checklist_gate  —— Writer 之后：仅 opt-in 时 interrupt；approve 写 checklist，deny 清空
                     （故意不调任何外部 tracker；清单只进图状态 / 本地 memo）

Researcher 如何检查权限标志：只读 state["web_enabled"]；为 False 时绝不调用 WebSearchPort。
清单开关如何进状态：start API → run.produce_checklist → service 注入初始 JudgmentState。
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from langgraph.types import interrupt

from judgment_forge.citation.policy import (
    Claim,
    CitationAnchor,
    EvidenceSnippet,
    evaluate_claims,
)
from judgment_forge.materials.service import MaterialService
from judgment_forge.provider.agent_chat import complete_for_agent
from judgment_forge.provider.port import ChatMessage, ChatProvider
from judgment_forge.runs.state import (
    ClaimDict,
    EvidenceDict,
    JudgmentState,
    MemoDict,
)
from judgment_forge.runs.trace import emit_trace
from judgment_forge.web.port import WebSearchPort

# Critic→Researcher 最大打回次数，防止图死循环；超过后 Writer 仍须产出诚实备忘录。
MAX_CRITIC_BOUNCES = 2

# 行动清单定稿条数窗口（工单 09）：批准后落库须落在此区间。
CHECKLIST_MIN_ITEMS = 3
CHECKLIST_MAX_ITEMS = 8


def _normalize_checklist_items(items: list[str], *, question: str) -> list[str]:
    """
    把草稿收成 3–8 条非空行动项；不足则用确定性兜底补齐，超出则截断。

    意图：闸门批准后的落库形状稳定，不依赖模型一次吐对条数。
    """
    cleaned = [item.strip() for item in items if item and str(item).strip()]
    cleaned = [str(item) for item in cleaned]
    fallbacks = [
        f"复核备忘录结论是否覆盖「{question[:48]}」",
        "对照材料锚点核对关键事实主张",
        "把标注为推断/未知的句子列入补证清单",
        "与干系人确认选项对比中的优先路径",
        "记录本次拒绝联网时缺失的外部证据缺口",
        "安排下一次研判前更新材料包",
        "把 next_steps 拆成可执行的责任人与截止日（人工）",
        "复查 Run Trace 中的 HITL 与 Critic 打回记录",
    ]
    for item in fallbacks:
        if len(cleaned) >= CHECKLIST_MIN_ITEMS:
            break
        if item not in cleaned:
            cleaned.append(item)
    while len(cleaned) < CHECKLIST_MIN_ITEMS:
        cleaned.append(f"跟进研判后续动作 #{len(cleaned) + 1}")
    return cleaned[:CHECKLIST_MAX_ITEMS]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型回复里尽力抠出 JSON 对象；失败返回 None（走确定性兜底）。"""
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def make_planner_node(provider: ChatProvider):
    """
    构造 Planner 节点：问模型要子问题；解析失败则用原问题当唯一子问题。

    意图：给 Researcher 一张「查什么」清单，而不是一次吞整题。
    """

    def planner(state: JudgmentState) -> dict[str, Any]:
        question = state["question"]
        raw = complete_for_agent(
            provider,
            [
                ChatMessage(
                    role="system",
                    content=(
                        "你是研判 Planner。只输出 JSON："
                        '{"sub_questions":["..."]}。不要自行联网。'
                    ),
                ),
                ChatMessage(role="user", content=question),
            ],
        )
        parsed = _extract_json_object(raw)
        plan: list[str] = []
        if parsed and isinstance(parsed.get("sub_questions"), list):
            plan = [
                str(q).strip()
                for q in parsed["sub_questions"]
                if str(q).strip()
            ]
        if not plan:
            plan = [question]
        return {"plan": plan, "critic_feedback": "", "ready_for_writer": False}

    return planner


def make_web_gate_node():
    """
    构造联网 HITL 闸门节点：用 LangGraph interrupt 暂停，等人 approve/deny。

    建模要点：
      - interrupt(payload) 把 run 停在本节点；service 把状态写成 waiting_for_human；
      - 人经 POST .../hitl 提交决定后，service 用 Command(resume=decision) 续跑；
      - resume 后 interrupt() 返回该决定，本函数再写 web_enabled / web_hitl_decision；
      - 批准前 Researcher 看不到 web_enabled=True，故 WebSearchPort 不会被调用。
    """

    def web_gate(state: JudgmentState) -> dict[str, Any]:
        # 若状态里已有决定（例如从 checkpoint 重入），直接兑现，避免二次 interrupt。
        existing = state.get("web_hitl_decision")
        if existing in ("approve", "deny"):
            return {
                "web_enabled": existing == "approve",
                "web_hitl_decision": existing,
            }

        decision = interrupt(
            {
                "gate": "web",
                "prompt": "是否允许本次研判使用联网/搜索工具？",
            }
        )
        # API 层已校验 approve|deny；非法 resume 视为协议错误，不静默当 deny。
        if decision not in ("approve", "deny"):
            raise ValueError(f"invalid web HITL decision: {decision!r}")
        return {
            "web_enabled": decision == "approve",
            "web_hitl_decision": decision,
        }

    return web_gate


def make_researcher_node(
    provider: ChatProvider,
    materials: MaterialService,
    web_search: WebSearchPort,
):
    """
    构造 Researcher 节点：按 plan 检索材料包；仅当 web_enabled 时再调联网端口。

    权限标志检查：
      - state["web_enabled"] 为真 → 调用 web_search.search，主张锚点带 url + retrieved_at；
      - 否则只走 MaterialService.search，绝不触碰 WebSearchPort（HITL 批准前的硬约束）。
    """

    def researcher(state: JudgmentState) -> dict[str, Any]:
        project_id = UUID(state["project_id"])
        owner_id = UUID(state["owner_id"])
        plan = state.get("plan") or [state["question"]]
        feedback = (state.get("critic_feedback") or "").strip()
        web_enabled = bool(state.get("web_enabled"))

        _ = complete_for_agent(
            provider,
            [
                ChatMessage(
                    role="system",
                    content=(
                        "你是 Researcher。根据材料笔记起草主张。"
                        f"{'已批准联网时可引用网页。' if web_enabled else '禁止联网。'}"
                        "若有打回意见必须修正锚点。"
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=(
                        f"问题：{state['question']}\n"
                        f"子问题：{plan}\n"
                        f"打回意见：{feedback or '（无）'}"
                    ),
                ),
            ],
        )

        evidence: list[EvidenceDict] = []
        claims: list[ClaimDict] = []
        seen_material: set[tuple[str, str]] = set()
        seen_web: set[str] = set()

        for sub_q in plan:
            emit_trace(
                kind="tool",
                name="materials.search",
                query=sub_q,
            )
            hits = materials.search(owner_id, project_id, sub_q, limit=5)
            for hit in hits:
                mid = str(hit.material_id)
                key = (mid, hit.location_hint)
                if key in seen_material:
                    continue
                seen_material.add(key)
                snippet = hit.content.strip()
                if not snippet:
                    continue
                evidence.append(
                    {
                        "material_id": mid,
                        "location_hint": hit.location_hint,
                        "text": snippet,
                    }
                )
                claims.append(
                    {
                        "text": snippet[:500],
                        "presented_as": "fact",
                        "anchors": [
                            {
                                "material_id": mid,
                                "location_hint": hit.location_hint,
                            }
                        ],
                    }
                )

        # 权限闸：仅 web_enabled 才进入 WebSearchPort；批准前 call_count 必须保持 0。
        if web_enabled:
            for sub_q in plan:
                emit_trace(
                    kind="tool",
                    name="web_search.search",
                    query=sub_q,
                )
                for web_hit in web_search.search(sub_q, limit=2):
                    if web_hit.url in seen_web:
                        continue
                    seen_web.add(web_hit.url)
                    retrieved = web_hit.retrieved_at.isoformat()
                    snippet = web_hit.snippet.strip() or web_hit.title
                    evidence.append(
                        {
                            "url": web_hit.url,
                            "retrieved_at": retrieved,
                            "text": snippet,
                        }
                    )
                    claims.append(
                        {
                            "text": snippet[:500],
                            "presented_as": "fact",
                            "anchors": [
                                {
                                    "url": web_hit.url,
                                    "retrieved_at": retrieved,
                                }
                            ],
                        }
                    )

        if not claims:
            claims.append(
                {
                    "text": (
                        f"材料包中未检索到与「{state['question']}」直接对应的证据"
                        "（推断/未知）。"
                    ),
                    "presented_as": "inference",
                    "anchors": [],
                }
            )

        if feedback:
            claims = [
                c
                for c in claims
                if c["presented_as"] != "fact" or c.get("anchors")
            ]
            if not claims:
                claims.append(
                    {
                        "text": "经 Critic 打回后仍缺可核验材料锚点（推断/未知）。",
                        "presented_as": "inference",
                        "anchors": [],
                    }
                )

        return {"evidence": evidence, "claims": claims}

    return researcher


def make_critic_node():
    """
    构造 Critic 节点：对 Researcher 主张套 CitationPolicy。

    裁决如何影响边（边在 graph.route_after_critic）：
      - 任一 bounce 且未超 MAX → ready_for_writer=False，bounce_count+1，写 feedback；
      - 否则 ready_for_writer=True（mark_inference 放行，由 Writer 标明推断/未知）。
    Critic 本身不调模型——产品规则已在纯函数里，避免「prompt 里再讲一遍锚点」。
    """

    def critic(state: JudgmentState) -> dict[str, Any]:
        raw_claims = state.get("claims") or []
        raw_evidence = state.get("evidence") or []
        claims = [
            Claim(
                text=c["text"],
                presented_as=c.get("presented_as", "inference"),
                anchors=tuple(
                    CitationAnchor(
                        material_id=str(a.get("material_id") or ""),
                        location_hint=str(a.get("location_hint") or ""),
                        url=str(a.get("url") or ""),
                        retrieved_at=str(a.get("retrieved_at") or ""),
                    )
                    for a in (c.get("anchors") or [])
                ),
            )
            for c in raw_claims
        ]
        evidence = [
            EvidenceSnippet(
                material_id=str(e.get("material_id") or ""),
                location_hint=str(e.get("location_hint") or ""),
                text=e.get("text", ""),
                url=str(e.get("url") or ""),
                retrieved_at=str(e.get("retrieved_at") or ""),
            )
            for e in raw_evidence
        ]
        decisions = evaluate_claims(claims, evidence)
        bounce_reasons = [
            d.reason for d in decisions if d.outcome == "bounce"
        ]
        bounce_count = int(state.get("bounce_count") or 0)

        if bounce_reasons and bounce_count < MAX_CRITIC_BOUNCES:
            next_count = bounce_count + 1
            emit_trace(
                kind="critic_bounce",
                bounce_count=next_count,
                reasons=bounce_reasons,
            )
            return {
                "ready_for_writer": False,
                "bounce_count": next_count,
                "critic_feedback": "；".join(bounce_reasons),
            }

        if bounce_reasons:
            fixed: list[ClaimDict] = []
            for claim, decision in zip(raw_claims, decisions, strict=True):
                if decision.outcome == "bounce":
                    fixed.append(
                        {
                            "text": claim["text"],
                            "presented_as": "inference",
                            "anchors": claim.get("anchors") or [],
                        }
                    )
                else:
                    fixed.append(claim)
            return {
                "claims": fixed,
                "ready_for_writer": True,
                "critic_feedback": "",
                "bounce_count": bounce_count,
            }

        return {
            "ready_for_writer": True,
            "critic_feedback": "",
            "bounce_count": bounce_count,
        }

    return critic


def make_writer_node(provider: ChatProvider):
    """
    构造 Writer 节点：把通过 Critic 的主张收成决策备忘录四段。

    必填：conclusion / options / risks_unknowns / next_steps；
    claims 原样带入（含材料锚点、联网 url+时间，或 inference 标记）。

    清单：仅当 state.produce_checklist 为真时起草 checklist_draft（3–8 条候选），
    此时不定稿——定稿权在其后的 checklist_gate（第二道硬闸门）。
    """

    def writer(state: JudgmentState) -> dict[str, Any]:
        claims = state.get("claims") or []
        question = state["question"]
        claims_blob = json.dumps(claims, ensure_ascii=False)
        want_checklist = bool(state.get("produce_checklist"))

        system = (
            "你是 Writer。只输出 JSON，键为 conclusion, options, "
            "risks_unknowns, next_steps"
            + (", checklist" if want_checklist else "")
            + "。材料主张须保留锚点语义；联网主张保留 URL 与检索时间；"
            "无锚点句须体现推断/未知。"
        )
        if want_checklist:
            system += (
                "若含 checklist：给出 3–8 条可人工执行的行动项字符串数组；"
                "不要创建外部工单，只列本地跟进项。"
            )

        raw = complete_for_agent(
            provider,
            [
                ChatMessage(role="system", content=system),
                ChatMessage(
                    role="user",
                    content=f"问题：{question}\n主张：{claims_blob}",
                ),
            ],
        )
        parsed = _extract_json_object(raw)

        def _section(key: str, fallback: str) -> str:
            if parsed and isinstance(parsed.get(key), str) and parsed[key].strip():
                return str(parsed[key]).strip()
            return fallback

        fact_lines = [
            c["text"] for c in claims if c.get("presented_as") == "fact"
        ]
        inference_lines = [
            c["text"] for c in claims if c.get("presented_as") == "inference"
        ]

        memo: MemoDict = {
            "conclusion": _section(
                "conclusion",
                (
                    f"针对「{question}」，基于材料包："
                    + ("；".join(fact_lines[:3]) if fact_lines else "证据有限，结论偏暂定。")
                ),
            ),
            "options": _section(
                "options",
                (
                    "选项对比："
                    + (
                        " / ".join(fact_lines[:4])
                        if fact_lines
                        else "材料未给出可对比选项，待补充证据。"
                    )
                ),
            ),
            "risks_unknowns": _section(
                "risks_unknowns",
                (
                    "风险与未知："
                    + (
                        "；".join(inference_lines)
                        if inference_lines
                        else "主要未知在于材料覆盖面是否足够。"
                    )
                ),
            ),
            "next_steps": _section(
                "next_steps",
                "建议下一步：复核备忘录中带锚点的主张，并对标注为推断/未知的句子补证。",
            ),
            "claims": claims,
        }

        out: dict[str, Any] = {"memo": memo, "checklist_draft": None, "checklist": None}
        if want_checklist:
            raw_items: list[str] = []
            if parsed and isinstance(parsed.get("checklist"), list):
                raw_items = [str(x) for x in parsed["checklist"]]
            out["checklist_draft"] = _normalize_checklist_items(
                raw_items, question=question
            )
        return out

    return writer


def make_checklist_gate_node():
    """
    构造行动清单 HITL 闸门：位于 Writer 之后的第二道硬闸门。

    相对 Writer 的位置：Writer 可起草 checklist_draft，但本节点才决定是否定稿。
    控制流：
      - produce_checklist=False → 直接放行，checklist=None（opt-out 永不产出）；
      - opt-in → interrupt(gate=checklist，载荷含草稿条文供人审)；
        approve 采用 Writer 已规范化的草稿（3–8）；deny 清空清单，memo 仍落库；
      - 故意不调用 GitHub/Jira/任何外部 tracker——产品是研判工具，不是静默 RPA。
    """

    def checklist_gate(state: JudgmentState) -> dict[str, Any]:
        if not state.get("produce_checklist"):
            return {
                "checklist": None,
                "checklist_hitl_decision": None,
                "checklist_draft": None,
            }

        existing = state.get("checklist_hitl_decision")
        draft = list(state.get("checklist_draft") or [])
        question = state.get("question") or ""
        # Writer 侧已规范化；此处只截断上限，避免批准时再静默「代写」新条。
        finalized = [str(item).strip() for item in draft if str(item).strip()]
        finalized = finalized[:CHECKLIST_MAX_ITEMS]
        if len(finalized) < CHECKLIST_MIN_ITEMS:
            finalized = _normalize_checklist_items(finalized, question=question)

        if existing in ("approve", "deny"):
            return {
                "checklist": finalized if existing == "approve" else None,
                "checklist_hitl_decision": existing,
            }

        decision = interrupt(
            {
                "gate": "checklist",
                "prompt": "是否定稿并保存本次行动清单？（拒绝则仅保留决策备忘录，不写外部系统）",
                "draft": finalized,
                "draft_count": len(finalized),
            }
        )
        if decision not in ("approve", "deny"):
            raise ValueError(f"invalid checklist HITL decision: {decision!r}")
        return {
            "checklist": finalized if decision == "approve" else None,
            "checklist_hitl_decision": decision,
        }

    return checklist_gate
