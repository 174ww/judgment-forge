"""
为何存在：验收 CitationPolicy 第二测试缝——主张+证据 → pass / mark_inference / bounce，
        且无 DB/网络（工单 06）。
谁调用：pytest。
调用谁：judgment_forge.citation（纯函数与值对象）。
"""

from __future__ import annotations

from judgment_forge.citation import (
    Claim,
    CitationAnchor,
    EvidenceSnippet,
    evaluate_claims,
)


def test_claim_with_matching_anchor_passes():
    """材料主张挂有与证据一致的锚点 → pass。"""
    evidence = [
        EvidenceSnippet(
            material_id="mat-1",
            location_hint="p.3",
            text="自研编排可审计。",
        )
    ]
    claims = [
        Claim(
            text="自研编排可审计。",
            presented_as="fact",
            anchors=(CitationAnchor(material_id="mat-1", location_hint="p.3"),),
        )
    ]

    decisions = evaluate_claims(claims, evidence)

    assert len(decisions) == 1
    assert decisions[0].outcome == "pass"
    assert decisions[0].claim_index == 0


def test_unanchored_claim_already_marked_inference():
    """无锚点但已标为推断/未知 → mark_inference（允许写入备忘录，不得当事实）。"""
    claims = [
        Claim(
            text="托管方案长期成本更低。",
            presented_as="inference",
            anchors=(),
        )
    ]

    decisions = evaluate_claims(claims, evidence=[])

    assert decisions[0].outcome == "mark_inference"


def test_factual_claim_without_anchor_bounces():
    """无锚点却当事实陈述 → bounce（Critic 打回 Researcher）。"""
    claims = [
        Claim(
            text="百炼一定更快上线。",
            presented_as="fact",
            anchors=(),
        )
    ]

    decisions = evaluate_claims(claims, evidence=[])

    assert decisions[0].outcome == "bounce"


def test_anchor_not_in_evidence_treated_as_missing():
    """主张挂了锚点但证据集中找不到对应片段 → 视同无锚点。"""
    evidence = [
        EvidenceSnippet(material_id="mat-other", location_hint="§2", text="无关")
    ]
    claims = [
        Claim(
            text="材料里写了 X。",
            presented_as="fact",
            anchors=(CitationAnchor(material_id="mat-1", location_hint="p.1"),),
        )
    ]

    decisions = evaluate_claims(claims, evidence)

    assert decisions[0].outcome == "bounce"


def test_batch_mixed_outcomes():
    """一批主张可同时出现 pass / mark_inference / bounce。"""
    evidence = [
        EvidenceSnippet(material_id="m", location_hint="¶1", text="有据可查")
    ]
    claims = [
        Claim(
            text="有据可查",
            presented_as="fact",
            anchors=(CitationAnchor(material_id="m", location_hint="¶1"),),
        ),
        Claim(text="可能更贵", presented_as="inference", anchors=()),
        Claim(text="必然更贵", presented_as="fact", anchors=()),
    ]

    outcomes = [d.outcome for d in evaluate_claims(claims, evidence)]

    assert outcomes == ["pass", "mark_inference", "bounce"]


def test_web_anchor_with_url_and_retrieved_at_passes():
    """联网主张：锚点含 URL + 检索时间且证据集可核验 → pass。"""
    evidence = [
        EvidenceSnippet(
            url="https://example.com/doc",
            retrieved_at="2026-07-21T09:30:00+00:00",
            text="托管控制台不暴露步骤。",
        )
    ]
    claims = [
        Claim(
            text="托管控制台不暴露步骤。",
            presented_as="fact",
            anchors=(
                CitationAnchor(
                    url="https://example.com/doc",
                    retrieved_at="2026-07-21T09:30:00+00:00",
                ),
            ),
        )
    ]

    decisions = evaluate_claims(claims, evidence)

    assert decisions[0].outcome == "pass"
