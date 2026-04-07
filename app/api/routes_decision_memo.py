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

from fastapi import Query

from app.config import settings
from app.schemas.decision import (
    AuditTrailResponse,
    DecisionMemo,
    DecisionMemoRequest,
    HumanDecisionRequest,
    HumanDecisionResponse,
    PrioritizedListResponse,
    ProductPriority,
    SystemHealth,
    UpstreamStatus,
)
from app.services import decision_store, memo_service, prioritization_service, upstream_clients

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
    """Record a human decision with persistence and audit trail."""
    # Generate memo to capture system recommendation at decision time
    system_action = None
    confidence = None
    try:
        memo = await memo_service.generate_memo(request.product_id)
        system_action = memo.recommended_action
        confidence = memo.confidence
    except Exception:
        logger.warning("Could not generate memo for decision context: %s", request.product_id)

    result = decision_store.save_decision(
        product_id=request.product_id,
        action=request.action,
        note=request.note,
        system_action=system_action,
        confidence=confidence,
    )

    # Record metrics
    from app.services.metrics import metrics
    metrics.record_decision(request.action.value, result.agreed_with_system)

    return result


# ── GET /api/audit-trail ────────────────────────────────────────────

@router.get(
    "/audit-trail",
    response_model=AuditTrailResponse,
    summary="Аудит решений",
    description="История всех решений с agreement rate.",
)
async def get_audit_trail(limit: int = Query(100, ge=1, le=500)) -> AuditTrailResponse:
    """Get audit trail of all human decisions."""
    return decision_store.get_audit_trail(limit=limit)


# ── GET /api/decisions/{product_id} ─────────────────────────────────

@router.get(
    "/decisions/{product_id}",
    summary="История решений по продукту",
)
async def get_product_decisions(product_id: str):
    """Get decision history for a specific product."""
    entries = decision_store.get_decisions(product_id=product_id, limit=50)
    return {"product_id": product_id, "entries": entries, "total": len(entries)}


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
    # Phase 2: fetch real product IDs from TCS + scoring candidates
    product_ids = await _collect_product_ids()
    memos = await memo_service.generate_memos_batch(product_ids)

    # Phase 7: smart ranking via prioritization_service
    sorted_memos = prioritization_service.rank_memos(memos)

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


# ── GET /api/system/metrics ──────────────────────────────────────────

@router.get(
    "/system/metrics",
    summary="Метрики сервиса",
    description="In-memory счётчики: memos, decisions, latency, LLM, errors.",
)
async def get_metrics():
    """Get service metrics snapshot."""
    from app.services.metrics import metrics
    return metrics.snapshot()


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


# ── Helpers ──────────────────────────────────────────────────────────

async def _collect_product_ids() -> list[str]:
    """Collect product IDs from scored candidates + TCS products."""
    import httpx

    ids: list[str] = []
    seen: set[str] = set()

    def _add(pid: str):
        if pid and pid not in seen:
            ids.append(pid)
            seen.add(pid)

    # 1. Scored candidates (those that actually have scores)
    try:
        headers = {"X-API-Key": settings.SCORING_API_KEY}
        async with httpx.AsyncClient(timeout=8.0) as client:
            # Check candidates 1-10 for scores
            for cid in range(1, 11):
                resp = await client.get(
                    f"{settings.SCORING_SERVICE_URL}/api/scoring/candidates/{cid}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("final_score") is not None:
                        _add(str(cid))
    except Exception as e:
        logger.warning("Failed to fetch scoring candidates: %s", e)

    # 2. TCS products (YUYU catalog)
    try:
        headers = {"X-API-Key": settings.TCS_API_KEY}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.TCS_URL}/api/products", headers=headers)
            if resp.status_code == 200:
                for p in resp.json():
                    sku = p.get("sku")
                    if sku:
                        _add(sku)
    except Exception as e:
        logger.warning("Failed to fetch TCS products: %s", e)

    # Fallback: mock IDs if nothing found
    if not ids:
        ids = list(upstream_clients.MOCK_PRODUCTS.keys())
        logger.info("No real products found, using mock data")

    return ids
