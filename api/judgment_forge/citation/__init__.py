"""
为何存在：引用策略包入口——对外只暴露「主张/证据/裁决」值对象与纯函数 evaluate_*。
谁调用：后续 Critic（工单 07）；本包单测；日后 Writer 若需复检也可依赖。
调用谁：policy 模块（真正的规则实现）。
"""

from judgment_forge.citation.policy import (
    Claim,
    ClaimDecision,
    ClaimPresentation,
    CitationAnchor,
    EvidenceSnippet,
    PolicyOutcome,
    evaluate_claim,
    evaluate_claims,
)

__all__ = [
    "Claim",
    "ClaimDecision",
    "ClaimPresentation",
    "CitationAnchor",
    "EvidenceSnippet",
    "PolicyOutcome",
    "evaluate_claim",
    "evaluate_claims",
]
