"""API Routes — Decision Memo endpoints.

Endpoints:
  POST /api/decision-memo         — generate memo for product
  GET  /api/decision-memo/{id}    — get cached/stored memo (Phase 5)
  POST /api/human-decision        — record human decision (Phase 5)
  GET  /api/products/prioritized  — prioritized review queue
  GET  /api/system/decision-health — system health
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.decision import (
    DecisionMemo,
    DecisionMemoRequest,
    HumanDecisionRequest,
    HumanDecisionResponse,
    PrioritizedListResponse,
    ProductPriority,
    SystemHealth,
    UpstreamStatus,
)
from app.services import memo_service, upstream_clients

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["decision-memo"])


# ── POST /api/decision-memo ─────────────────────────────────────────

@router.post(
    "/decision-memo",
    response_model=DecisionMemo,
    summary="Сгенерировать Decision Memo",
    description="Собирает данные, применяет правила, возвращает рекомендацию. "
                "Финальное решение ВСЕГДА за человеком.",
)
async def create_decision_memo(request: DecisionMemoRequest) -> DecisionMemo:
    """Generate a decision memo for the given product."""
    try:
        memo = await memo_service.generate_memo(
            product_id=request.product_id,
            force_refresh=request.force_refresh,
        )
        return memo
    except Exception as e:
        logger.exception("Failed to generate memo for %s", request.product_id)
        raise HTTPException(status_code=500, detail=f"Memo generation failed: {e}")


# ── GET /api/decision-memo/{product_id} ─────────────────────────────

@router.get(
    "/decision-memo/{product_id}",
    response_model=DecisionMemo,
    summary="Получить Decision Memo",
    description="Генерирует memo на лету. Phase 5: будет брать из кеша/БД.",
)
async def get_decision_memo(product_id: str) -> DecisionMemo:
    """Get decision memo for product. Currently generates on-the-fly."""
    try:
        memo = await memo_service.generate_memo(product_id=product_id)
        return memo
    except Exception as e:
        logger.exception("Failed to get memo for %s", product_id)
        raise HTTPException(status_code=500, detail=f"Memo retrieval failed: {e}")


# ── POST /api/human-decision ────────────────────────────────────────

@router.post(
    "/human-decision",
    response_model=HumanDecisionResponse,
    summary="Записать решение человека",
    description="Сохраняет финальное решение (approve/reject/watch). Phase 5: persistence.",
)
async def record_human_decision(request: HumanDecisionRequest) -> HumanDecisionResponse:
    """Record a human decision. Phase 5: will persist to database."""
    # TODO Phase 5: persist to database, link to memo
    import uuid

    logger.info(
        "Human decision recorded: product=%s action=%s note=%s",
        request.product_id, request.action.value, request.note,
    )

    return HumanDecisionResponse(
        id=str(uuid.uuid4()),
        product_id=request.product_id,
        action=request.action,
        note=request.note,
        decided_at=datetime.now(timezone.utc),
        memo_snapshot=None,  # TODO Phase 5: attach memo snapshot
    )


# ── GET /api/products/prioritized ───────────────────────────────────

@router.get(
    "/products/prioritized",
    response_model=PrioritizedListResponse,
    summary="Приоритизированный список продуктов",
    description="Возвращает продукты, отсортированные по приоритету для разбора.",
)
async def get_prioritized_products() -> PrioritizedListResponse:
    """Get prioritized list of products for review.

    Ranking logic:
      1. BUY_CANDIDATE first, then WATCH, then REJECT
      2. Within group: higher confidence first
      3. Red flags push items up (need attention)
    """
    # Phase 1: use mock product IDs
    product_ids = list(upstream_clients.MOCK_PRODUCTS.keys())
    memos = await memo_service.generate_memos_batch(product_ids)

    # Sort: BUY_CANDIDATE > WATCH > REJECT, then by confidence desc, then red_flags desc
    action_order = {"BUY_CANDIDATE": 0, "WATCH": 1, "REJECT": 2}

    sorted_memos = sorted(
        memos,
        key=lambda m: (
            action_order.get(m.recommended_action.value, 3),
            -len(m.red_flags),  # more flags = higher priority (needs attention)
            -m.confidence,
        ),
    )

    products = [
        ProductPriority(
            product_id=m.product_id,
            recommended_action=m.recommended_action,
            confidence=m.confidence,
            pcs=m.scores.PCS,
            red_flag_count=len(m.red_flags),
            missing_data_count=len(m.unknowns),
            summary=m.summary,
            rank=i + 1,
        )
        for i, m in enumerate(sorted_memos)
    ]

    return PrioritizedListResponse(
        products=products,
        total=len(products),
        generated_at=datetime.now(timezone.utc),
    )


# ── GET /api/system/decision-health ─────────────────────────────────

@router.get(
    "/system/decision-health",
    response_model=SystemHealth,
    summary="Здоровье системы",
    description="Проверяет доступность upstream сервисов.",
)
async def check_health() -> SystemHealth:
    """Check system health and upstream availability."""
    from app.services.rule_engine import RULE_ENGINE_VERSION

    upstreams_config = [
        ("scoring-service", settings.SCORING_SERVICE_URL),
        ("demand-layer", settings.DEMAND_LAYER_URL),
        ("traffic-commerce", settings.TCS_URL),
    ]

    upstream_statuses = []
    for name, url in upstreams_config:
        result = await upstream_clients.check_upstream_health(name, url)
        upstream_statuses.append(UpstreamStatus(**result))

    all_healthy = all(u.healthy for u in upstream_statuses)
    any_healthy = any(u.healthy for u in upstream_statuses)

    if all_healthy:
        status = "healthy"
    elif any_healthy:
        status = "degraded"
    else:
        status = "unhealthy"

    return SystemHealth(
        status=status,
        version=settings.APP_VERSION,
        rule_engine_version=RULE_ENGINE_VERSION,
        upstreams=upstream_statuses,
        checked_at=datetime.now(timezone.utc),
    )
