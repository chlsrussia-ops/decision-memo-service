"""Rule Engine — deterministic verdict and confidence calculation.

Rules version: 1.0.0

Verdict rules (based on PCS):
  PCS >= 75  → BUY_CANDIDATE
  PCS 50–74  → WATCH
  PCS < 50   → REJECT
  PCS = None → REJECT (insufficient data)

Confidence calculation:
  Base confidence from PCS distance to thresholds.
  Reduced by: missing data, red flags, low source diversity.

Red flag rules (override trust):
  - OTRS is null → score reliability unknown
  - buy_intent_ratio < 0.02 → weak purchase signal
  - source_count <= 1 → single source, can't cross-validate
  - SRS > 60 → market overheated / saturated
"""

from __future__ import annotations

from app.models.domain import UpstreamData
from app.schemas.decision import (
    DecisionFactors,
    DecisionRecommendation,
    MissingData,
    RecommendedAction,
    RedFlag,
    RedFlagCode,
)

RULE_ENGINE_VERSION = "1.0.0"

# ── Thresholds ───────────────────────────────────────────────────────

PCS_BUY_THRESHOLD = 75
PCS_WATCH_THRESHOLD = 50
SRS_OVERHEAT_THRESHOLD = 60
BUY_INTENT_MIN = 0.02
MIN_SOURCES = 2


# ── Verdict ──────────────────────────────────────────────────────────

def compute_verdict(data: UpstreamData) -> RecommendedAction:
    """Determine recommended action based on PCS."""
    if data.pcs is None:
        return RecommendedAction.REJECT
    if data.pcs >= PCS_BUY_THRESHOLD:
        return RecommendedAction.BUY_CANDIDATE
    if data.pcs >= PCS_WATCH_THRESHOLD:
        return RecommendedAction.WATCH
    return RecommendedAction.REJECT


# ── Red Flags ────────────────────────────────────────────────────────

def detect_red_flags(data: UpstreamData) -> list[RedFlag]:
    """Detect conditions that override trust in the score."""
    flags: list[RedFlag] = []

    if data.otrs is None:
        flags.append(RedFlag(
            code=RedFlagCode.OTRS_NULL,
            severity="high",
            message="OTRS отсутствует — надёжность score неизвестна",
            detail="Organic Traffic Relevance Score не рассчитан. "
                   "Невозможно оценить органический потенциал.",
        ))

    if data.buy_intent_ratio is not None and data.buy_intent_ratio < BUY_INTENT_MIN:
        flags.append(RedFlag(
            code=RedFlagCode.LOW_BUY_INTENT,
            severity="high",
            message=f"Buy intent {data.buy_intent_ratio:.1%} — ниже порога {BUY_INTENT_MIN:.0%}",
            detail="Низкая доля покупательского намерения в поисковых запросах.",
        ))

    if data.source_count is not None and data.source_count < MIN_SOURCES:
        flags.append(RedFlag(
            code=RedFlagCode.SINGLE_SOURCE,
            severity="critical",
            message="Только 1 источник сигнала — нельзя кросс-валидировать",
            detail="Данные получены из единственного источника. "
                   "Высокий риск ложного сигнала.",
        ))

    if data.srs is not None and data.srs > SRS_OVERHEAT_THRESHOLD:
        flags.append(RedFlag(
            code=RedFlagCode.MARKET_OVERHEATED,
            severity="high",
            message=f"SRS={data.srs:.0f} — рынок перегрет (порог {SRS_OVERHEAT_THRESHOLD})",
            detail="Высокая конкуренция и насыщение рынка. "
                   "Входить дорого, маржа под давлением.",
        ))

    return flags


# ── Missing Data ─────────────────────────────────────────────────────

def detect_missing_data(data: UpstreamData) -> list[MissingData]:
    """Identify data gaps that reduce confidence."""
    missing: list[MissingData] = []

    if data.pcs is None:
        missing.append(MissingData(
            field="PCS",
            impact="critical",
            description="Композитный score не рассчитан — verdict ненадёжен",
        ))

    if data.tvs is None:
        missing.append(MissingData(
            field="TVS",
            impact="medium",
            description="Trend Velocity Score отсутствует",
        ))

    if data.pucs is None:
        missing.append(MissingData(
            field="PuCS",
            impact="medium",
            description="Purchase Confidence Score отсутствует",
        ))

    if data.otrs is None:
        missing.append(MissingData(
            field="OTRS",
            impact="high",
            description="Organic Traffic Relevance Score отсутствует",
        ))

    if data.srs is None:
        missing.append(MissingData(
            field="SRS",
            impact="medium",
            description="Supply/Risk Saturation Score отсутствует",
        ))

    if data.buy_intent_ratio is None:
        missing.append(MissingData(
            field="buy_intent_ratio",
            impact="medium",
            description="Доля покупательского намерения неизвестна",
        ))

    if data.search_volume is None:
        missing.append(MissingData(
            field="search_volume",
            impact="low",
            description="Объём поисковых запросов неизвестен",
        ))

    if not data.scoring_available:
        missing.append(MissingData(
            field="scoring_service",
            impact="critical",
            description="Scoring service недоступен — данные отсутствуют",
        ))

    if not data.demand_available:
        missing.append(MissingData(
            field="demand_layer",
            impact="high",
            description="Demand layer недоступен — спрос не оценён",
        ))

    return missing


# ── Confidence ───────────────────────────────────────────────────────

def compute_confidence(
    data: UpstreamData,
    red_flags: list[RedFlag],
    missing: list[MissingData],
) -> float:
    """Calculate confidence 0.0–1.0.

    Logic:
    - Start at 1.0
    - Each critical missing: -0.25
    - Each high missing: -0.15
    - Each medium missing: -0.08
    - Each critical red flag: -0.20
    - Each high red flag: -0.12
    - If PCS is None: cap at 0.15
    - Floor at 0.05
    """
    confidence = 1.0

    impact_penalties = {"critical": 0.25, "high": 0.15, "medium": 0.08, "low": 0.03}
    severity_penalties = {"critical": 0.20, "high": 0.12}

    for m in missing:
        confidence -= impact_penalties.get(m.impact, 0.05)

    for f in red_flags:
        confidence -= severity_penalties.get(f.severity, 0.05)

    if data.pcs is None:
        confidence = min(confidence, 0.15)

    return max(round(confidence, 2), 0.05)


# ── Decision Factors ─────────────────────────────────────────────────

def determine_factors(data: UpstreamData, verdict: RecommendedAction) -> DecisionFactors:
    """Identify primary and secondary factors driving the recommendation."""
    if data.pcs is None:
        return DecisionFactors(
            primary="Недостаточно данных для расчёта PCS",
            secondary=None,
        )

    if verdict == RecommendedAction.BUY_CANDIDATE:
        primary = f"PCS={data.pcs:.0f} выше порога {PCS_BUY_THRESHOLD}"
        secondary = _secondary_positive(data)
    elif verdict == RecommendedAction.WATCH:
        primary = f"PCS={data.pcs:.0f} в зоне наблюдения ({PCS_WATCH_THRESHOLD}–{PCS_BUY_THRESHOLD})"
        secondary = _secondary_neutral(data)
    else:
        primary = f"PCS={data.pcs:.0f} ниже порога {PCS_WATCH_THRESHOLD}"
        secondary = _secondary_negative(data)

    return DecisionFactors(primary=primary, secondary=secondary)


def _secondary_positive(data: UpstreamData) -> str | None:
    parts = []
    if data.tvs is not None and data.tvs >= 60:
        parts.append(f"сильный тренд (TVS={data.tvs:.0f})")
    if data.pucs is not None and data.pucs >= 60:
        parts.append(f"высокая покупательная уверенность (PuCS={data.pucs:.0f})")
    if data.buy_intent_ratio is not None and data.buy_intent_ratio >= 0.05:
        parts.append(f"buy intent {data.buy_intent_ratio:.1%}")
    return "; ".join(parts) if parts else None


def _secondary_neutral(data: UpstreamData) -> str | None:
    parts = []
    if data.srs is not None and data.srs > 40:
        parts.append(f"умеренная конкуренция (SRS={data.srs:.0f})")
    if data.tvs is not None and data.tvs < 40:
        parts.append(f"слабый тренд (TVS={data.tvs:.0f})")
    return "; ".join(parts) if parts else None


def _secondary_negative(data: UpstreamData) -> str | None:
    parts = []
    if data.srs is not None and data.srs > SRS_OVERHEAT_THRESHOLD:
        parts.append(f"рынок перегрет (SRS={data.srs:.0f})")
    if data.buy_intent_ratio is not None and data.buy_intent_ratio < BUY_INTENT_MIN:
        parts.append(f"слабый buy intent ({data.buy_intent_ratio:.1%})")
    return "; ".join(parts) if parts else None


# ── Why Buy ──────────────────────────────────────────────────────────

def build_why_buy(data: UpstreamData) -> list[str]:
    """Build list of positive factors supporting a buy decision."""
    reasons: list[str] = []

    if data.pcs is not None and data.pcs >= PCS_BUY_THRESHOLD:
        reasons.append(f"Композитный score PCS={data.pcs:.0f} — выше порога закупки")

    if data.tvs is not None and data.tvs >= 60:
        reasons.append(f"Сильный тренд: TVS={data.tvs:.0f}")

    if data.pucs is not None and data.pucs >= 60:
        reasons.append(f"Высокая покупательная уверенность: PuCS={data.pucs:.0f}")

    if data.buy_intent_ratio is not None and data.buy_intent_ratio >= 0.05:
        reasons.append(f"Хороший buy intent: {data.buy_intent_ratio:.1%}")

    if data.search_volume is not None and data.search_volume >= 5000:
        reasons.append(f"Высокий объём поиска: {data.search_volume:,}")

    if data.srs is not None and data.srs < 30:
        reasons.append(f"Низкая конкуренция: SRS={data.srs:.0f}")

    if data.source_count is not None and data.source_count >= 3:
        reasons.append(f"Кросс-валидация: {data.source_count} источников")

    return reasons


# ── Full Evaluation ──────────────────────────────────────────────────

def evaluate(data: UpstreamData) -> dict:
    """Run full rule engine evaluation.

    Returns dict with: verdict, confidence, red_flags, missing_data,
    why_buy, decision_factors.
    """
    verdict = compute_verdict(data)
    red_flags = detect_red_flags(data)
    missing = detect_missing_data(data)
    confidence = compute_confidence(data, red_flags, missing)
    factors = determine_factors(data, verdict)
    why_buy = build_why_buy(data)

    return {
        "verdict": verdict,
        "confidence": confidence,
        "red_flags": red_flags,
        "missing_data": missing,
        "why_buy": why_buy,
        "decision_factors": factors,
    }
