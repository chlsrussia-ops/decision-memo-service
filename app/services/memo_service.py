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
from app.services import explanation_service, llm_summary_service, memo_cache, risk_service, rule_engine, upstream_clients
from app.services.metrics import metrics

logger = logging.getLogger(__name__)


async def generate_memo(product_id: str, force_refresh: bool = False) -> DecisionMemo:
    """Generate a complete decision memo for a product.

    This is the single entry point — one call, full memo.
    """
    # 0. Check cache
    if not force_refresh:
        cached = memo_cache.get(product_id)
        if cached:
            return cached

    # 1. Fetch upstream data
    # Route: PROD-xxx → mock data, everything else → real upstream
    if product_id.startswith("PROD-"):
        data = await upstream_clients.fetch_mock_data(product_id)
        logger.info("Mock data loaded for %s", product_id)
    else:
        data = await upstream_clients.fetch_upstream_data(product_id)
        logger.info(
            "Upstream data fetched for %s in %dms (scoring=%s, demand=%s, analytics=%s)",
            product_id, data.latency_ms, data.scoring_available,
            data.demand_available, data.analytics_available,
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

    # 5. Build next action suggestion
    next_action = explanation_service.build_next_action(
        verdict=evaluation["verdict"],
        confidence=evaluation["confidence"],
        red_flags=evaluation["red_flags"],
        missing=evaluation["missing_data"],
        risks=risks,
    )

    # 6. Data completeness (how many of 5 core scores available)
    available = sum(1 for v in [data.tvs, data.pucs, data.srs, data.otrs, data.pcs] if v is not None)
    data_completeness = round(available / 5, 2)

    # 7. Assemble memo
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
        next_action=next_action,
        data_completeness=data_completeness,
        human_required=True,
        rule_engine_version=rule_engine.RULE_ENGINE_VERSION,
        generated_at=datetime.now(timezone.utc),
        upstream_latency_ms=data.latency_ms,
    )

    # 8. LLM summary enhancement (optional, non-blocking)
    from app.config import settings as _cfg
    if _cfg.LLM_ENABLED and _cfg.ANTHROPIC_API_KEY:
        try:
            llm_summary = await llm_summary_service.enhance_summary(memo)
            if llm_summary:
                memo.summary = llm_summary
                metrics.record_llm(success=True)
            else:
                metrics.record_llm(success=False)
        except Exception as e:
            metrics.record_llm(success=False)
            logger.warning("LLM enhancement skipped for %s: %s", product_id, e)

    # 9. Record metrics
    metrics.record_memo(memo.recommended_action.value, data.latency_ms)
    if data.errors:
        metrics.record_upstream_error()

    # 10. Cache result
    memo_cache.put(product_id, memo)

    logger.info(
        "Memo generated for %s: action=%s confidence=%.2f flags=%d risks=%d latency=%dms",
        product_id, memo.recommended_action.value, memo.confidence,
        len(memo.red_flags), len(memo.risks), data.latency_ms,
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
