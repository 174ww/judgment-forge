"""
为何存在：研判工坊的「引用策略」产品规则——材料主张须有可核验锚点；
        联网主张须有 URL + 检索时间；做不到锚定的句子只能标「推断/未知」。
        这是 spec 里可选的第二测试缝：纯函数、无 I/O，便于单测 Critic 规则。

产品规则（编码进 evaluate_claims）：
  1. 主张的材料锚点能在证据集中命中（material_id + location_hint）→ pass
  2. 主张带有效联网锚点（url + retrieved_at）→ pass（HITL 批准后的网页引用）
  3. 无有效锚点，且已标为推断/未知（presented_as=inference）→ mark_inference
  4. 无有效锚点，却当事实陈述（presented_as=fact）→ bounce

谁调用：Critic 节点（runs.nodes.make_critic_node）对每条研究主张调用本模块；
        若任一 outcome=bounce → 打回 Researcher；
        mark_inference → 允许进入 Writer，但备忘录须标明「推断/未知」；
        全部 pass → 正常进入 Writer。
        单元测试直接调用。
调用谁：无（标准库 typing / dataclasses only）——刻意不碰 DB、网络、Provider。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

ClaimPresentation = Literal["fact", "inference"]
PolicyOutcome = Literal["pass", "mark_inference", "bounce"]


@dataclass(frozen=True)
class CitationAnchor:
    """
    引用锚点：材料（document id + 位置）或联网（url + retrieved_at）。

    材料与联网字段可并存于类型上，但一条锚点语义上只应填一类；
    策略分别用 _is_web_anchor / 材料键 判断。
    """

    material_id: str = ""
    location_hint: str = ""
    url: str = ""
    retrieved_at: str = ""


@dataclass(frozen=True)
class EvidenceSnippet:
    """
    候选证据片段。

    材料证据：material_id + location_hint；
    联网证据：url + retrieved_at（text 为摘要）。策略只核验锚点是否可对上，不解读语义。
    """

    material_id: str = ""
    location_hint: str = ""
    text: str = ""
    url: str = ""
    retrieved_at: str = ""


@dataclass(frozen=True)
class Claim:
    """
    一条待检主张。

    presented_as=fact：写成「材料/事实如此」——必须有有效锚点，否则 bounce。
    presented_as=inference：已承认是推断或未知——无锚点时 mark_inference，不得升级为事实。
    """

    text: str
    presented_as: ClaimPresentation
    anchors: tuple[CitationAnchor, ...] = ()


@dataclass(frozen=True)
class ClaimDecision:
    """单条主张的策略裁决；Critic 聚合 bounce / mark_inference 决定是否打回。"""

    claim_index: int
    outcome: PolicyOutcome
    reason: str


def _is_web_anchor(anchor: CitationAnchor) -> bool:
    """联网锚点：必须同时有 URL 与检索时间（工单 08）。"""
    return bool(anchor.url.strip() and anchor.retrieved_at.strip())


def _evidence_material_keys(
    evidence: Sequence[EvidenceSnippet],
) -> set[tuple[str, str]]:
    """材料证据压成 (material_id, location_hint) 集合。"""
    return {
        (e.material_id, e.location_hint)
        for e in evidence
        if e.material_id and e.location_hint
    }


def _evidence_web_keys(
    evidence: Sequence[EvidenceSnippet],
) -> set[tuple[str, str]]:
    """联网证据压成 (url, retrieved_at) 集合。"""
    return {
        (e.url, e.retrieved_at)
        for e in evidence
        if e.url.strip() and e.retrieved_at.strip()
    }


def _has_supported_anchor(
    claim: Claim,
    material_keys: set[tuple[str, str]],
    web_keys: set[tuple[str, str]],
) -> bool:
    """主张是否至少有一个锚点能在对应证据集中核验（材料或联网）。"""
    for a in claim.anchors:
        if _is_web_anchor(a) and (a.url, a.retrieved_at) in web_keys:
            return True
        if (
            a.material_id
            and a.location_hint
            and (a.material_id, a.location_hint) in material_keys
        ):
            return True
    return False


def _decide(
    claim: Claim,
    material_keys: set[tuple[str, str]],
    web_keys: set[tuple[str, str]],
    *,
    claim_index: int,
) -> ClaimDecision:
    """在已构建的证据键集上裁决单条主张（供 evaluate_* 复用）。"""
    if _has_supported_anchor(claim, material_keys, web_keys):
        return ClaimDecision(
            claim_index=claim_index,
            outcome="pass",
            reason="主张锚点已在证据集中核验",
        )

    if claim.presented_as == "inference":
        return ClaimDecision(
            claim_index=claim_index,
            outcome="mark_inference",
            reason="无有效锚点；已标推断/未知，不得写成事实",
        )

    return ClaimDecision(
        claim_index=claim_index,
        outcome="bounce",
        reason="无有效锚点却当事实陈述；Critic 应打回 Researcher",
    )


def evaluate_claim(
    claim: Claim,
    evidence: Sequence[EvidenceSnippet],
    *,
    claim_index: int = 0,
) -> ClaimDecision:
    """
    对单条主张套用引用策略。

    Critic 路径：Researcher 产出主张列表 → 对本函数逐条（或对 evaluate_claims）
    → 根据 outcome 决定打回 / 要求标推断 / 放行。
    """
    return _decide(
        claim,
        _evidence_material_keys(evidence),
        _evidence_web_keys(evidence),
        claim_index=claim_index,
    )


def evaluate_claims(
    claims: Sequence[Claim],
    evidence: Sequence[EvidenceSnippet],
) -> list[ClaimDecision]:
    """
    批量裁决：保持输入顺序，claim_index 与 claims 下标一致。

    Critic 常见用法：any(d.outcome == "bounce" for d in decisions) → 打回；
    否则把 mark_inference 的主张交给 Writer 显式标注。
    """
    material_keys = _evidence_material_keys(evidence)
    web_keys = _evidence_web_keys(evidence)
    return [
        _decide(
            claim,
            material_keys,
            web_keys,
            claim_index=index,
        )
        for index, claim in enumerate(claims)
    ]
