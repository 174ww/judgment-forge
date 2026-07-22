"""
为何存在：研判图的共享状态与决策备忘录值对象——节点之间只经此形状传数据。
谁调用：runs.graph / runs.nodes（读写图状态）；runs.service（把终态 memo/checklist 落库、
        读 HITL 标志、cancel 时标 cancelled）。
调用谁：无（typing / dataclasses）。

清单开关：produce_checklist 在 start 时写入 run 行并注入初始图状态；
  Writer 仅在其为真时写 checklist_draft；checklist_gate 批准后才有 checklist；
  落库时由 service 把 checklist 并进 memo JSONB（故意不做 GitHub/Jira 等外部写入）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict

ClaimPresentation = Literal["fact", "inference"]
RunStatus = Literal[
    "queued",
    "running",
    "waiting_for_human",
    "completed",
    "failed",
    "cancelled",
]
HitlDecision = Literal["approve", "deny"]


class ClaimDict(TypedDict, total=False):
    """图内主张的字典形状（便于 LangGraph 序列化）。"""

    text: str
    presented_as: ClaimPresentation
    # 材料锚点：material_id + location_hint；联网锚点：url + retrieved_at
    anchors: list[dict[str, str]]


class EvidenceDict(TypedDict, total=False):
    material_id: str
    location_hint: str
    text: str
    url: str
    retrieved_at: str


class MemoDict(TypedDict):
    """
    决策备忘录：必填四段 + claims；checklist 仅在第二道闸批准后由 service 并入落库。

    图内 Writer 只写四段与 claims；清单草稿走 checklist_draft，不进本 dict。
    """

    conclusion: str
    options: str
    risks_unknowns: str
    next_steps: str
    claims: list[ClaimDict]
    checklist: NotRequired[list[str]]


class JudgmentState(TypedDict, total=False):
    """
    LangGraph 状态袋。

    控制流读写约定：
      Planner         写 plan；
      web_gate        经 interrupt/resume 写 web_enabled / web_hitl_decision；
      Researcher      读 web_enabled：仅 True 时调 WebSearchPort；写 evidence / claims；
      Critic          写 critic_feedback / bounce_count / ready_for_writer；
      Writer          写 memo；若 produce_checklist 另写 checklist_draft（不定稿）；
      checklist_gate  仅 opt-in 时 interrupt；approve 写 checklist，deny 清空。
    """

    question: str
    project_id: str
    owner_id: str
    produce_checklist: bool
    web_enabled: bool
    web_hitl_decision: HitlDecision | None
    plan: list[str]
    evidence: list[EvidenceDict]
    claims: list[ClaimDict]
    critic_feedback: str
    bounce_count: int
    ready_for_writer: bool
    memo: MemoDict | None
    checklist_draft: list[str] | None
    checklist: list[str] | None
    checklist_hitl_decision: HitlDecision | None
    error: str | None


@dataclass(frozen=True)
class PublicClaimAnchor:
    material_id: str = ""
    location_hint: str = ""
    url: str = ""
    retrieved_at: str = ""


@dataclass(frozen=True)
class PublicMemoClaim:
    text: str
    presented_as: ClaimPresentation
    anchors: tuple[PublicClaimAnchor, ...] = ()


@dataclass(frozen=True)
class PublicDecisionMemo:
    conclusion: str
    options: str
    risks_unknowns: str
    next_steps: str
    claims: tuple[PublicMemoClaim, ...] = field(default_factory=tuple)
    # 仅 opt-in 且 checklist 闸批准后非空；拒绝 / opt-out 为 None。
    checklist: tuple[str, ...] | None = None


def memo_from_dict(data: dict[str, Any]) -> PublicDecisionMemo:
    """把图终态 / JSONB 行收成对外 PublicDecisionMemo。"""
    claims: list[PublicMemoClaim] = []
    for raw in data.get("claims") or []:
        anchors = tuple(
            PublicClaimAnchor(
                material_id=str(a.get("material_id") or ""),
                location_hint=str(a.get("location_hint") or ""),
                url=str(a.get("url") or ""),
                retrieved_at=str(a.get("retrieved_at") or ""),
            )
            for a in (raw.get("anchors") or [])
        )
        claims.append(
            PublicMemoClaim(
                text=str(raw["text"]),
                presented_as=raw.get("presented_as", "inference"),
                anchors=anchors,
            )
        )
    raw_checklist = data.get("checklist")
    checklist: tuple[str, ...] | None = None
    if isinstance(raw_checklist, list) and raw_checklist:
        checklist = tuple(str(item).strip() for item in raw_checklist if str(item).strip())
        if not checklist:
            checklist = None
    return PublicDecisionMemo(
        conclusion=str(data.get("conclusion") or ""),
        options=str(data.get("options") or ""),
        risks_unknowns=str(data.get("risks_unknowns") or ""),
        next_steps=str(data.get("next_steps") or ""),
        claims=tuple(claims),
        checklist=checklist,
    )


def memo_to_dict(memo: PublicDecisionMemo | MemoDict) -> dict[str, Any]:
    """备忘录 → 可 JSON 序列化的 dict（落库 / API）；无清单时不写 checklist 键。"""
    if isinstance(memo, dict):
        out = dict(memo)
        if not out.get("checklist"):
            out.pop("checklist", None)
        return out
    body: dict[str, Any] = {
        "conclusion": memo.conclusion,
        "options": memo.options,
        "risks_unknowns": memo.risks_unknowns,
        "next_steps": memo.next_steps,
        "claims": [
            {
                "text": c.text,
                "presented_as": c.presented_as,
                "anchors": [
                    {
                        k: v
                        for k, v in {
                            "material_id": a.material_id,
                            "location_hint": a.location_hint,
                            "url": a.url,
                            "retrieved_at": a.retrieved_at,
                        }.items()
                        if v
                    }
                    for a in c.anchors
                ],
            }
            for c in memo.claims
        ],
    }
    if memo.checklist:
        body["checklist"] = list(memo.checklist)
    return body
