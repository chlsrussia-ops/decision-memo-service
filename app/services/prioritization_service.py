"""Prioritization Service — smart ranking for product review queue.

Ranking factors (weighted):
  1. Recommendation tier: BUY > WATCH > REJECT (primary sort)
  2. Attention urgency: red flags push items UP (need review)
  3. Confidence: higher confidence = more actionable
  4. Data completeness: more data = easier to decide
  5. Freshness penalty: stale scores get lower priority

Goal: surface the most actionable items first — strong candidates
AND dangerous edge cases that need human attention.
"""

from __future__ import annotations

from app.schemas.decision import DecisionMemo, RecommendedAction


# Tier weights (lower = higher priority)
_TIER = {
    RecommendedAction.BUY_CANDIDATE: 0,
    RecommendedAction.WATCH: 1,
    RecommendedAction.REJECT: 2,
}


def compute_priority_score(memo: DecisionMemo) -> float:
    """Compute a single priority score for sorting (lower = higher priority).

    Components:
      tier:       0/1/2 based on recommendation (×100)
      urgency:    red_flag_count × -10 (more flags = higher priority)
      confidence: -confidence × 20 (higher confidence = higher priority)
      completeness: -(data_completeness or 0) × 5
    """
    tier = _TIER.get(memo.recommended_action, 3) * 100
    urgency = -len(memo.red_flags) * 10
    confidence = -memo.confidence * 20
    completeness = -(memo.data_completeness or 0) * 5

    return tier + urgency + confidence + completeness


def rank_memos(memos: list[DecisionMemo]) -> list[DecisionMemo]:
    """Sort memos by priority score (most actionable first)."""
    return sorted(memos, key=compute_priority_score)
