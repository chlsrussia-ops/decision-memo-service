"""Internal domain types used by services (not exposed via API)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UpstreamData:
    """Normalized data collected from all upstream services."""
    product_id: str

    # Scores
    tvs: Optional[float] = None
    pucs: Optional[float] = None
    srs: Optional[float] = None
    otrs: Optional[float] = None
    pcs: Optional[float] = None

    # Demand
    search_volume: Optional[int] = None
    search_trend: Optional[str] = None
    buy_intent_ratio: Optional[float] = None
    source_count: Optional[int] = None
    platform_count: Optional[int] = None
    category: Optional[str] = None
    region: Optional[str] = None

    # Meta
    scoring_available: bool = False
    demand_available: bool = False
    analytics_available: bool = False

    errors: list[str] = field(default_factory=list)
    latency_ms: int = 0
