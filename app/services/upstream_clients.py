"""Upstream Clients — fetch data from scoring, demand, and analytics services.

Phase 1 (MVP): returns mock data for development/testing.
Phase 2: real HTTP calls with retries, timeouts, fallbacks.

Each client returns partial UpstreamData fields.
The memo_service merges them into a single UpstreamData.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.config import settings
from app.models.domain import UpstreamData

logger = logging.getLogger(__name__)

# ── Mock Data (Phase 1) ─────────────────────────────────────────────

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
    "PROD-004": {
        "tvs": 65, "pucs": 70, "srs": 35, "otrs": 55, "pcs": 68,
        "search_volume": 8000, "search_trend": "rising",
        "buy_intent_ratio": 0.06, "source_count": 3, "platform_count": 2,
        "category": "beauty", "region": "RU",
    },
    "PROD-005": {
        "tvs": 90, "pucs": 88, "srs": 15, "otrs": 80, "pcs": 89,
        "search_volume": 25000, "search_trend": "rising",
        "buy_intent_ratio": 0.12, "source_count": 5, "platform_count": 4,
        "category": "gadgets", "region": "RU",
    },
    "PROD-006": {
        "tvs": None, "pucs": None, "srs": None, "otrs": None, "pcs": None,
        "search_volume": None, "search_trend": None,
        "buy_intent_ratio": None, "source_count": None, "platform_count": None,
        "category": "unknown", "region": "RU",
    },
    "PROD-007": {
        "tvs": 85, "pucs": 75, "srs": 65, "otrs": 70, "pcs": 78,
        "search_volume": 15000, "search_trend": "stable",
        "buy_intent_ratio": 0.07, "source_count": 3, "platform_count": 3,
        "category": "sports", "region": "RU",
    },
    "PROD-008": {
        "tvs": 45, "pucs": 50, "srs": 55, "otrs": 35, "pcs": 48,
        "search_volume": 3000, "search_trend": "falling",
        "buy_intent_ratio": 0.015, "source_count": 2, "platform_count": 1,
        "category": "toys", "region": "RU",
    },
}


async def fetch_mock_data(product_id: str) -> UpstreamData:
    """Return mock data for Phase 1 development."""
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
        tvs=mock.get("tvs"),
        pucs=mock.get("pucs"),
        srs=mock.get("srs"),
        otrs=mock.get("otrs"),
        pcs=mock.get("pcs"),
        search_volume=mock.get("search_volume"),
        search_trend=mock.get("search_trend"),
        buy_intent_ratio=mock.get("buy_intent_ratio"),
        source_count=mock.get("source_count"),
        platform_count=mock.get("platform_count"),
        category=mock.get("category"),
        region=mock.get("region"),
        scoring_available=mock.get("pcs") is not None,
        demand_available=mock.get("search_volume") is not None,
        analytics_available=True,
    )


# ── Real Clients (Phase 2 stubs) ────────────────────────────────────

async def fetch_scoring(product_id: str) -> dict:
    """Fetch scores from scoring-service. TODO: Phase 2 integration."""
    # TODO: GET {SCORING_SERVICE_URL}/api/scores/{product_id}
    raise NotImplementedError("Phase 2: scoring-service integration")


async def fetch_demand(product_id: str) -> dict:
    """Fetch demand data from desired-demand-layer. TODO: Phase 2 integration."""
    # TODO: GET {DEMAND_LAYER_URL}/api/demand/{product_id}
    raise NotImplementedError("Phase 2: demand-layer integration")


async def fetch_analytics(product_id: str) -> dict:
    """Fetch analytics from TCS. TODO: Phase 2 integration."""
    # TODO: GET {TCS_URL}/api/analytics/{product_id}
    raise NotImplementedError("Phase 2: TCS integration")


async def fetch_upstream_data(product_id: str) -> UpstreamData:
    """Fetch and merge data from all upstream services.

    Phase 1: uses mock data.
    Phase 2: parallel calls to real services with fallback.
    """
    start = time.monotonic()

    # Phase 1: mock
    data = await fetch_mock_data(product_id)

    data.latency_ms = int((time.monotonic() - start) * 1000)
    return data


# ── Health Check ─────────────────────────────────────────────────────

async def check_upstream_health(name: str, url: str) -> dict:
    """Check if an upstream service is reachable."""
    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/health")
            latency = int((time.monotonic() - start) * 1000)
            return {
                "name": name,
                "healthy": resp.status_code == 200,
                "latency_ms": latency,
            }
    except Exception as e:
        return {
            "name": name,
            "healthy": False,
            "error": str(e),
        }
