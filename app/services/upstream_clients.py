"""Upstream Clients — fetch data from scoring, demand, and analytics services.

Phase 2: real HTTP calls to:
  - Trend Cloud API (:8003) — scoring with 6 sub-scores
  - DDL (:8090) — demand intelligence (in-memory, needs signal input)
  - TCS (:8400) — product catalog, DVL hypotheses, analytics

Score mapping (upstream 0.0–1.0 → our 0–100):
  trend_score         → TVS
  creative_test_score → OTRS (closest to organic traffic relevance)
  commerce_potential   → PuCS
  1 - market_saturation → SRS (inverted: their 1.0=open market, our 100=saturated)
  final_score          → PCS

Fallback: if upstream is down, returns partial data with errors noted.
Mock data preserved for testing with PROD-xxx IDs.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.config import settings
from app.models.domain import UpstreamData

logger = logging.getLogger(__name__)

# ── Score Mapping ────────────────────────────────────────────────────

def _to_100(val: Optional[float]) -> Optional[float]:
    """Convert 0.0–1.0 score to 0–100."""
    if val is None:
        return None
    return round(val * 100, 1)


def _invert_to_100(val: Optional[float]) -> Optional[float]:
    """Invert and convert: their 1.0=good → our 0=good (100=saturated)."""
    if val is None:
        return None
    return round((1.0 - val) * 100, 1)


# ── HTTP Client Factory ─────────────────────────────────────────────

def _client(timeout: float = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout or settings.UPSTREAM_TIMEOUT)


async def _get_with_retry(
    url: str,
    headers: dict = None,
    retries: int = None,
) -> Optional[dict]:
    """GET with retries. Returns parsed JSON or None on failure."""
    max_retries = retries or settings.UPSTREAM_RETRIES
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            async with _client() as client:
                resp = await client.get(url, headers=headers or {})
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    logger.warning("Not found: %s", url)
                    return None
                else:
                    last_error = f"HTTP {resp.status_code}"
                    logger.warning("Attempt %d: %s → %s", attempt + 1, url, last_error)
        except Exception as e:
            last_error = str(e)
            logger.warning("Attempt %d: %s → %s", attempt + 1, url, last_error)

    logger.error("All retries exhausted for %s: %s", url, last_error)
    return None


async def _post_with_retry(
    url: str,
    json_data: dict,
    headers: dict = None,
) -> Optional[dict]:
    """POST with retries."""
    max_retries = settings.UPSTREAM_RETRIES
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            async with _client() as client:
                resp = await client.post(url, json=json_data, headers=headers or {})
                if resp.status_code == 200:
                    return resp.json()
                else:
                    last_error = f"HTTP {resp.status_code}"
                    logger.warning("POST attempt %d: %s → %s", attempt + 1, url, last_error)
        except Exception as e:
            last_error = str(e)
            logger.warning("POST attempt %d: %s → %s", attempt + 1, url, last_error)

    logger.error("All POST retries exhausted for %s: %s", url, last_error)
    return None


# ── Scoring Service (Trend Cloud :8003) ──────────────────────────────

async def fetch_scoring(product_id: str) -> dict:
    """Fetch scores from Trend Cloud scoring API.

    Accepts:
      - numeric candidate_id (e.g. "1", "42")
      - product_id that maps to a candidate

    Returns dict with score fields or empty dict on failure.
    """
    headers = {"X-API-Key": settings.SCORING_API_KEY}
    base = settings.SCORING_SERVICE_URL

    # Try direct candidate lookup if numeric
    candidate_id = product_id
    if product_id.isdigit():
        url = f"{base}/api/scoring/candidates/{candidate_id}"
        data = await _get_with_retry(url, headers=headers)
        if data:
            return data

    # Try via intelligence product search
    url = f"{base}/api/intelligence/products/{product_id}"
    data = await _get_with_retry(url, headers=headers)
    if data and "id" in data:
        cid = data["id"]
        score_url = f"{base}/api/scoring/candidates/{cid}"
        score_data = await _get_with_retry(score_url, headers=headers)
        if score_data:
            return score_data

    return {}


async def fetch_commerce_decision(product_id: str) -> dict:
    """Fetch commerce decision from Trend Cloud."""
    headers = {"X-API-Key": settings.SCORING_API_KEY}
    base = settings.SCORING_SERVICE_URL

    if product_id.isdigit():
        url = f"{base}/api/commerce-decisions/candidates/{product_id}"
        data = await _get_with_retry(url, headers=headers)
        if data:
            return data
    return {}


# ── Demand Layer (DDL :8090) ─────────────────────────────────────────

async def fetch_demand(product_id: str, topic: str = None) -> dict:
    """Fetch demand data from DDL.

    DDL is in-memory and requires POST with signals.
    For Phase 2, we try to GET existing case first,
    then fall back to a lightweight POST if needed.
    """
    base = settings.DEMAND_LAYER_URL

    # Try listing existing cases with matching topic
    cases = await _get_with_retry(f"{base}/api/v1/demand-cases")
    if cases and isinstance(cases, list):
        for case in cases:
            case_topic = case.get("topic", "")
            if product_id.lower() in case_topic.lower() or (topic and topic.lower() in case_topic.lower()):
                case_id = case.get("id")
                if case_id:
                    report = await _get_with_retry(f"{base}/api/v1/demand-cases/{case_id}/report")
                    if report:
                        return {"case": case, "report": report}
                    return {"case": case}

    return {}


# ── TCS (Traffic Commerce System :8400) ──────────────────────────────

async def fetch_tcs_product(product_id: str) -> dict:
    """Fetch product data from TCS catalog."""
    headers = {"X-API-Key": settings.TCS_API_KEY}
    base = settings.TCS_URL

    # Get all products and find by SKU or ID
    products = await _get_with_retry(f"{base}/api/products", headers=headers)
    if products and isinstance(products, list):
        for p in products:
            if p.get("sku") == product_id or p.get("id") == product_id:
                return p

    return {}


async def fetch_tcs_hypothesis(product_id: str) -> dict:
    """Fetch DVL hypothesis for product from TCS."""
    headers = {"X-API-Key": settings.TCS_API_KEY}
    base = settings.TCS_URL

    hypotheses = await _get_with_retry(f"{base}/api/dvl/hypotheses", headers=headers)
    if hypotheses and isinstance(hypotheses, list):
        for h in hypotheses:
            sku = h.get("sku", "")
            category = h.get("category", "")
            # Match by SKU, ID, or category
            if (product_id == sku or product_id == h.get("id")
                    or product_id.lower() in sku.lower()):
                return h

    return {}


async def fetch_tcs_analytics() -> dict:
    """Fetch analytics overview from TCS."""
    headers = {"X-API-Key": settings.TCS_API_KEY}
    base = settings.TCS_URL
    return await _get_with_retry(f"{base}/api/analytics/overview", headers=headers) or {}


async def fetch_tcs_market_signals(product_id: str) -> list:
    """Fetch market signals from TCS."""
    headers = {"X-API-Key": settings.TCS_API_KEY}
    base = settings.TCS_URL
    data = await _get_with_retry(f"{base}/api/market-signals", headers=headers)
    if data and isinstance(data, list):
        return data
    if data and isinstance(data, dict):
        return data.get("items", data.get("signals", []))
    return []


# ── Unified Fetch ────────────────────────────────────────────────────

async def fetch_upstream_data(product_id: str) -> UpstreamData:
    """Fetch and merge data from all upstream services.

    Tries all three sources in parallel (conceptually).
    Normalizes scores to 0–100 scale.
    Records errors for each failed source.
    """
    start = time.monotonic()
    errors: list[str] = []
    data = UpstreamData(product_id=product_id)

    # 1. Scoring service
    try:
        scoring = await fetch_scoring(product_id)
        if scoring:
            data.tvs = _to_100(scoring.get("trend_score"))
            data.pucs = _to_100(scoring.get("commerce_potential_score"))
            data.srs = _invert_to_100(scoring.get("market_saturation_score"))
            data.otrs = _to_100(scoring.get("creative_test_score"))
            data.pcs = _to_100(scoring.get("final_score"))
            data.scoring_available = True
            logger.info("Scoring data loaded for %s: PCS=%.1f", product_id, data.pcs or 0)
        else:
            errors.append("scoring-service: no data")
    except Exception as e:
        errors.append(f"scoring-service: {e}")
        logger.error("Scoring fetch failed for %s: %s", product_id, e)

    # 2. TCS — product + hypothesis + analytics
    try:
        product = await fetch_tcs_product(product_id)
        hypothesis = await fetch_tcs_hypothesis(product_id)

        if product:
            data.category = product.get("category")
            data.region = "RU"
            data.analytics_available = True

        if hypothesis:
            data.analytics_available = True
            intent = hypothesis.get("intent_score")
            if intent is not None:
                data.buy_intent_ratio = round(intent, 4)
            confidence = hypothesis.get("confidence")
            decision = hypothesis.get("decision")
            # Source/platform count from experiments
            data.source_count = max(1, hypothesis.get("experiments_count", 0))
            data.platform_count = 1  # TCS is one platform
            if decision == "BUY":
                data.platform_count = 2  # validated = at least 2

        if not product and not hypothesis:
            errors.append("tcs: product not found")
    except Exception as e:
        errors.append(f"tcs: {e}")
        logger.error("TCS fetch failed for %s: %s", product_id, e)

    # 3. DDL — demand signals
    try:
        demand = await fetch_demand(product_id)
        if demand:
            case = demand.get("case", {})
            report = demand.get("report", {})
            demand_assessment = report.get("demand_assessment", {}) if report else {}

            ddi = case.get("confidence") or case.get("ddi_score")
            if ddi is not None and data.buy_intent_ratio is None:
                data.buy_intent_ratio = round(ddi, 4)

            if demand_assessment.get("demand_exists"):
                data.demand_available = True
                strength = demand_assessment.get("demand_strength")
                if strength and data.search_volume is None:
                    data.search_volume = int(strength * 100000)

                if demand_assessment.get("demand_sustainable"):
                    data.search_trend = "rising"
                elif demand_assessment.get("demand_monetizable"):
                    data.search_trend = "stable"
                else:
                    data.search_trend = "falling"
        else:
            errors.append("ddl: no matching case")
    except Exception as e:
        errors.append(f"ddl: {e}")
        logger.error("DDL fetch failed for %s: %s", product_id, e)

    # If no demand data but we have TCS product, mark demand as partial
    if not data.demand_available and data.analytics_available:
        data.demand_available = False

    data.errors = errors
    data.latency_ms = int((time.monotonic() - start) * 1000)
    return data


# ── Mock Data (kept for testing) ─────────────────────────────────────

MOCK_PRODUCTS: dict[str, dict] = {
    "PROD-001": {
        "tvs": 78, "pucs": 82, "srs": 25, "otrs": 65, "pcs": 81,
        "search_volume": 12000, "search_trend": "rising",
        "buy_intent_ratio": 0.08, "source_count": 4, "platform_count": 3,
        "category": "electronics", "region": "RU",
    },
    "PROD-002": {
        "tvs": 55, "pucs": 48, "srs": 45, "otrs": 40, "pcs": 58,
        "search_volume": 5000, "search_trend": "stable",
        "buy_intent_ratio": 0.03, "source_count": 2, "platform_count": 2,
        "category": "home", "region": "RU",
    },
    "PROD-003": {
        "tvs": 20, "pucs": 30, "srs": 72, "otrs": None, "pcs": 35,
        "search_volume": 800, "search_trend": "falling",
        "buy_intent_ratio": 0.01, "source_count": 1, "platform_count": 1,
        "category": "fashion", "region": "RU",
    },
    "PROD-005": {
        "tvs": 90, "pucs": 88, "srs": 15, "otrs": 80, "pcs": 89,
        "search_volume": 25000, "search_trend": "rising",
        "buy_intent_ratio": 0.12, "source_count": 5, "platform_count": 4,
        "category": "gadgets", "region": "RU",
    },
}


async def fetch_mock_data(product_id: str) -> UpstreamData:
    """Return mock data for PROD-xxx IDs (testing only)."""
    mock = MOCK_PRODUCTS.get(product_id)
    if mock is None:
        return UpstreamData(
            product_id=product_id,
            scoring_available=False,
            demand_available=False,
            analytics_available=False,
            errors=[f"Product {product_id} not found in mock dataset"],
        )
    return UpstreamData(
        product_id=product_id,
        tvs=mock.get("tvs"), pucs=mock.get("pucs"),
        srs=mock.get("srs"), otrs=mock.get("otrs"), pcs=mock.get("pcs"),
        search_volume=mock.get("search_volume"),
        search_trend=mock.get("search_trend"),
        buy_intent_ratio=mock.get("buy_intent_ratio"),
        source_count=mock.get("source_count"),
        platform_count=mock.get("platform_count"),
        category=mock.get("category"), region=mock.get("region"),
        scoring_available=mock.get("pcs") is not None,
        demand_available=mock.get("search_volume") is not None,
        analytics_available=True,
    )


# ── Health Check ─────────────────────────────────────────────────────

async def check_upstream_health(name: str, url: str) -> dict:
    """Check if an upstream service is reachable."""
    try:
        start = time.monotonic()
        async with _client(timeout=5.0) as client:
            resp = await client.get(f"{url}/health")
            latency = int((time.monotonic() - start) * 1000)
            return {"name": name, "healthy": resp.status_code == 200, "latency_ms": latency}
    except Exception as e:
        return {"name": name, "healthy": False, "error": str(e)}
