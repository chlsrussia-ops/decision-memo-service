"""Memo Service — orchestrates data collection, evaluation, and memo generation.

This is the main entry point for decision memo creation.
Flow:
  1. Fetch upstream data (scores, demand, analytics)
  2. Run rule engine (verdict, confidence, flags, missing)
  3. Assess risks
  4. Build explanation / summary
  5. Assemble DecisionMemo
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.domain import UpstreamData
from app.schemas.decision import (
    DecisionMemo,
    DemandSnapshot,
    ScoreSnapshot,
)
from app.services import explanation_service, risk_service, rule_engine, upstream_clients

logger = logging.getLogger(__name__)


async def generate_memo(product_id: str, force_refresh: bool = False) -> DecisionMemo:
    """Generate a complete decision memo for a product.

    This is the single entry point — one call, full memo.
    """
    # 1. Fetch upstream data
    data = await upstream_clients.fetch_upstream_data(product_id)
    logger.info(
        "Upstream data fetched for %s in %dms (scoring=%s, demand=%s)",
        product_id, data.latency_ms, data.scoring_available, data.demand_available,
    )

    # 2. Run rule engine
    evaluation = rule_engine.evaluate(data)

    # 3. Assess risks
    risks = risk_service.assess_risks(data)

    # 4. Build summary
    summary = explanation_service.build_summary(
        product_id=product_id,
        verdict=evaluation["verdict"],
        confidence=evaluation["confidence"],
        data=data,
        red_flags=evaluation["red_flags"],
        missing=evaluation["missing_data"],
    )

    # 5. Assemble memo
    memo = DecisionMemo(
        product_id=product_id,
        summary=summary,
        recommended_action=evaluation["verdict"],
        confidence=evaluation["confidence"],
        scores=_build_score_snapshot(data),
        demand=_build_demand_snapshot(data),
        why_buy=evaluation["why_buy"],
        risks=risks,
        unknowns=evaluation["missing_data"],
        red_flags=evaluation["red_flags"],
        decision_factors=evaluation["decision_factors"],
        human_required=True,
        rule_engine_version=rule_engine.RULE_ENGINE_VERSION,
        generated_at=datetime.now(timezone.utc),
        upstream_latency_ms=data.latency_ms,
    )

    logger.info(
        "Memo generated for %s: action=%s confidence=%.2f flags=%d risks=%d",
        product_id, memo.recommended_action.value, memo.confidence,
        len(memo.red_flags), len(memo.risks),
    )

    return memo


async def generate_memos_batch(product_ids: list[str]) -> list[DecisionMemo]:
    """Generate memos for multiple products."""
    memos = []
    for pid in product_ids:
        memo = await generate_memo(pid)
        memos.append(memo)
    return memos


def _build_score_snapshot(data: UpstreamData) -> ScoreSnapshot:
    return ScoreSnapshot(
        TVS=data.tvs,
        PuCS=data.pucs,
        SRS=data.srs,
        OTRS=data.otrs,
        PCS=data.pcs,
        scored_at=datetime.now(timezone.utc) if data.scoring_available else None,
    )


def _build_demand_snapshot(data: UpstreamData) -> DemandSnapshot | None:
    if not data.demand_available:
        return None
    return DemandSnapshot(
        search_volume=data.search_volume,
        search_trend=data.search_trend,
        buy_intent_ratio=data.buy_intent_ratio,
        source_count=data.source_count,
        platform_count=data.platform_count,
        category=data.category,
        region=data.region,
    )
