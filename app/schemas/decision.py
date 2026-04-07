"""Decision Memo Service — schemas and domain model.

Domain entities:
- DecisionMemoRequest: input for memo generation
- ScoreSnapshot: all scoring dimensions
- DemandSnapshot: demand signals
- RedFlag: detected risk override
- RiskFactor: identified risk
- MissingData: data gaps affecting confidence
- DecisionFactors: primary/secondary drivers
- DecisionRecommendation: verdict with explanation
- DecisionMemo: full memo response
- HumanDecisionRequest: human approve/reject/watch
- HumanDecisionResponse: stored human decision
- ProductPriority: prioritized product entry
- SystemHealth: service health status
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────

class RecommendedAction(str, Enum):
    BUY_CANDIDATE = "BUY_CANDIDATE"
    WATCH = "WATCH"
    REJECT = "REJECT"


class HumanAction(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    WATCH = "WATCH"


class RedFlagCode(str, Enum):
    OTRS_NULL = "OTRS_NULL"
    LOW_BUY_INTENT = "LOW_BUY_INTENT"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    MARKET_OVERHEATED = "MARKET_OVERHEATED"


# ── Score & Demand ───────────────────────────────────────────────────

class ScoreSnapshot(BaseModel):
    """All scoring dimensions at point-in-time."""
    TVS: Optional[float] = Field(None, description="Trend Velocity Score 0-100")
    PuCS: Optional[float] = Field(None, description="Purchase Confidence Score 0-100")
    SRS: Optional[float] = Field(None, description="Supply/Risk Saturation Score 0-100")
    OTRS: Optional[float] = Field(None, description="Organic Traffic Relevance Score 0-100")
    PCS: Optional[float] = Field(None, description="Product Composite Score 0-100")
    scored_at: Optional[datetime] = None


class DemandSnapshot(BaseModel):
    """Demand layer signals."""
    search_volume: Optional[int] = None
    search_trend: Optional[str] = Field(None, description="rising / stable / falling")
    buy_intent_ratio: Optional[float] = Field(None, description="0.0–1.0")
    source_count: Optional[int] = Field(None, description="Number of signal sources")
    platform_count: Optional[int] = Field(None, description="Number of platforms")
    category: Optional[str] = None
    region: Optional[str] = None


# ── Risk & Flags ─────────────────────────────────────────────────────

class RedFlag(BaseModel):
    """Detected red flag that overrides trust in score."""
    code: RedFlagCode
    severity: str = Field(..., description="high / critical")
    message: str
    detail: Optional[str] = None


class RiskFactor(BaseModel):
    """Identified risk — not necessarily a blocker."""
    factor: str
    level: str = Field(..., description="low / medium / high")
    description: str


class MissingData(BaseModel):
    """Data gap that reduces confidence."""
    field: str
    impact: str = Field(..., description="low / medium / high")
    description: str


# ── Decision ─────────────────────────────────────────────────────────

class DecisionFactors(BaseModel):
    """Primary and secondary factors driving recommendation."""
    primary: str
    secondary: Optional[str] = None


class DecisionRecommendation(BaseModel):
    """Machine recommendation — NOT a decision."""
    action: RecommendedAction
    confidence: float = Field(..., ge=0.0, le=1.0)
    factors: DecisionFactors


# ── API Request / Response ───────────────────────────────────────────

class DecisionMemoRequest(BaseModel):
    """Input for decision memo generation."""
    product_id: str = Field(..., min_length=1)
    force_refresh: bool = Field(False, description="Ignore cache, re-fetch upstream")


class DecisionMemo(BaseModel):
    """Full decision memo — the core output of the system."""
    product_id: str
    summary: str = Field(..., description="Human-readable 1-2 sentence brief")

    recommended_action: RecommendedAction
    confidence: float = Field(..., ge=0.0, le=1.0)

    scores: ScoreSnapshot
    demand: Optional[DemandSnapshot] = None

    why_buy: list[str] = Field(default_factory=list)
    risks: list[RiskFactor] = Field(default_factory=list)
    unknowns: list[MissingData] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)

    decision_factors: DecisionFactors
    next_action: Optional[str] = Field(None, description="Suggested next step for human")
    data_completeness: Optional[float] = Field(None, description="0.0-1.0 how much data we have")

    human_required: bool = Field(True, description="Always true — human decides")

    rule_engine_version: str
    generated_at: datetime
    upstream_latency_ms: Optional[int] = None


# ── Human Decision ──────────────────────────────────────────────────

class HumanDecisionRequest(BaseModel):
    """Human's final decision on a product."""
    product_id: str
    action: HumanAction
    note: Optional[str] = Field(None, description="Reason, especially if disagreeing with memo")
    memo_id: Optional[str] = Field(None, description="Reference to the memo being decided on")


class HumanDecisionResponse(BaseModel):
    """Stored human decision."""
    id: str
    product_id: str
    action: HumanAction
    note: Optional[str]
    decided_at: datetime
    recommended_action: Optional[RecommendedAction] = None
    confidence: Optional[float] = None
    agreed_with_system: Optional[bool] = None


class AuditEntry(BaseModel):
    """Single audit trail entry — human decision + system recommendation."""
    id: str
    product_id: str
    human_action: HumanAction
    system_action: Optional[RecommendedAction] = None
    confidence: Optional[float] = None
    agreed: Optional[bool] = None
    note: Optional[str] = None
    decided_at: datetime


class AuditTrailResponse(BaseModel):
    """Audit trail — all human decisions."""
    entries: list[AuditEntry]
    total: int
    agreement_rate: Optional[float] = None


# ── Prioritized List ────────────────────────────────────────────────

class ProductPriority(BaseModel):
    """Product in prioritized review queue."""
    product_id: str
    recommended_action: RecommendedAction
    confidence: float
    pcs: Optional[float] = None
    red_flag_count: int = 0
    missing_data_count: int = 0
    summary: str
    rank: int


class PrioritizedListResponse(BaseModel):
    """Prioritized list of products for review."""
    products: list[ProductPriority]
    total: int
    generated_at: datetime


# ── System Health ────────────────────────────────────────────────────

class UpstreamStatus(BaseModel):
    """Health status of an upstream service."""
    name: str
    healthy: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None


class SystemHealth(BaseModel):
    """Overall system health."""
    status: str = Field(..., description="healthy / degraded / unhealthy")
    version: str
    rule_engine_version: str
    upstreams: list[UpstreamStatus]
    checked_at: datetime
