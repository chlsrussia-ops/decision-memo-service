"""Rule Registry — tracks rule versions and change history.

Every change to thresholds, red flag conditions, or confidence
calculation is versioned here. This creates an audit trail for
understanding why a memo was generated a certain way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

CURRENT_VERSION = "1.0.0"

@dataclass
class RuleChange:
    version: str
    date: str
    description: str
    changes: list[str]


# Change log — append-only
RULE_HISTORY: list[RuleChange] = [
    RuleChange(
        version="1.0.0",
        date="2026-04-07",
        description="Initial rule engine",
        changes=[
            "PCS >= 75 → BUY_CANDIDATE",
            "PCS 50-74 → WATCH",
            "PCS < 50 → REJECT",
            "Red flags: OTRS_NULL, LOW_BUY_INTENT (<2%), SINGLE_SOURCE, MARKET_OVERHEATED (SRS>60)",
            "Confidence: base 1.0, penalties for missing data and red flags",
            "Score mapping: upstream 0-1 → internal 0-100",
        ],
    ),
]


def get_current_version() -> str:
    return CURRENT_VERSION


def get_history() -> list[dict]:
    return [
        {
            "version": r.version,
            "date": r.date,
            "description": r.description,
            "changes": r.changes,
        }
        for r in RULE_HISTORY
    ]


def get_current_rules() -> dict:
    """Return current rule configuration for transparency."""
    from app.services.rule_engine import (
        BUY_INTENT_MIN,
        MIN_SOURCES,
        PCS_BUY_THRESHOLD,
        PCS_WATCH_THRESHOLD,
        SRS_OVERHEAT_THRESHOLD,
    )

    return {
        "version": CURRENT_VERSION,
        "thresholds": {
            "pcs_buy": PCS_BUY_THRESHOLD,
            "pcs_watch": PCS_WATCH_THRESHOLD,
            "srs_overheat": SRS_OVERHEAT_THRESHOLD,
            "buy_intent_min": BUY_INTENT_MIN,
            "min_sources": MIN_SOURCES,
        },
        "red_flags": [
            {"code": "OTRS_NULL", "condition": "OTRS is None"},
            {"code": "LOW_BUY_INTENT", "condition": f"buy_intent < {BUY_INTENT_MIN:.0%}"},
            {"code": "SINGLE_SOURCE", "condition": f"source_count < {MIN_SOURCES}"},
            {"code": "MARKET_OVERHEATED", "condition": f"SRS > {SRS_OVERHEAT_THRESHOLD}"},
        ],
        "verdict_rules": [
            {"condition": f"PCS >= {PCS_BUY_THRESHOLD}", "action": "BUY_CANDIDATE"},
            {"condition": f"PCS {PCS_WATCH_THRESHOLD}-{PCS_BUY_THRESHOLD-1}", "action": "WATCH"},
            {"condition": f"PCS < {PCS_WATCH_THRESHOLD}", "action": "REJECT"},
            {"condition": "PCS is None", "action": "REJECT"},
        ],
    }
