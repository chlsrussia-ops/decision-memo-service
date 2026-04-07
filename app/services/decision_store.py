"""Decision Store — SQLite persistence for human decisions.

Stores:
- Human decisions (approve/reject/watch)
- System recommendation at time of decision
- Whether human agreed with system
- Notes explaining disagreement

Schema is simple — one table, no ORM, direct sqlite3.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.schemas.decision import (
    AuditEntry,
    AuditTrailResponse,
    HumanAction,
    HumanDecisionResponse,
    RecommendedAction,
)

logger = logging.getLogger(__name__)

DB_PATH = Path("/app/data/decisions.db")

# Action mapping for agreement check
_AGREE_MAP = {
    (HumanAction.APPROVE, RecommendedAction.BUY_CANDIDATE): True,
    (HumanAction.WATCH, RecommendedAction.WATCH): True,
    (HumanAction.REJECT, RecommendedAction.REJECT): True,
}


def _get_db() -> sqlite3.Connection:
    """Get database connection, creating table if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS human_decisions (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            human_action TEXT NOT NULL,
            system_action TEXT,
            confidence REAL,
            agreed INTEGER,
            note TEXT,
            decided_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_decisions_product
        ON human_decisions(product_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_decisions_date
        ON human_decisions(decided_at DESC)
    """)
    conn.commit()
    return conn


def save_decision(
    product_id: str,
    action: HumanAction,
    note: Optional[str] = None,
    system_action: Optional[RecommendedAction] = None,
    confidence: Optional[float] = None,
) -> HumanDecisionResponse:
    """Save a human decision to the database."""
    decision_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    agreed = _AGREE_MAP.get((action, system_action)) if system_action else None

    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO human_decisions
               (id, product_id, human_action, system_action, confidence, agreed, note, decided_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision_id,
                product_id,
                action.value,
                system_action.value if system_action else None,
                confidence,
                1 if agreed is True else (0 if agreed is False else None),
                note,
                now.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(
        "Decision saved: id=%s product=%s human=%s system=%s agreed=%s",
        decision_id, product_id, action.value,
        system_action.value if system_action else "?", agreed,
    )

    return HumanDecisionResponse(
        id=decision_id,
        product_id=product_id,
        action=action,
        note=note,
        decided_at=now,
        recommended_action=system_action,
        confidence=confidence,
        agreed_with_system=agreed,
    )


def get_decisions(
    product_id: Optional[str] = None,
    limit: int = 50,
) -> list[AuditEntry]:
    """Get decision history, optionally filtered by product."""
    conn = _get_db()
    try:
        if product_id:
            rows = conn.execute(
                "SELECT * FROM human_decisions WHERE product_id = ? ORDER BY decided_at DESC LIMIT ?",
                (product_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM human_decisions ORDER BY decided_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()

    return [_row_to_entry(r) for r in rows]


def get_audit_trail(limit: int = 100) -> AuditTrailResponse:
    """Get full audit trail with agreement rate."""
    entries = get_decisions(limit=limit)

    agreed_count = sum(1 for e in entries if e.agreed is True)
    total_with_system = sum(1 for e in entries if e.agreed is not None)
    agreement_rate = (
        round(agreed_count / total_with_system, 2) if total_with_system > 0 else None
    )

    return AuditTrailResponse(
        entries=entries,
        total=len(entries),
        agreement_rate=agreement_rate,
    )


def get_product_last_decision(product_id: str) -> Optional[AuditEntry]:
    """Get the most recent decision for a product."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM human_decisions WHERE product_id = ? ORDER BY decided_at DESC LIMIT 1",
            (product_id,),
        ).fetchone()
    finally:
        conn.close()

    return _row_to_entry(row) if row else None


def _row_to_entry(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        id=row["id"],
        product_id=row["product_id"],
        human_action=HumanAction(row["human_action"]),
        system_action=RecommendedAction(row["system_action"]) if row["system_action"] else None,
        confidence=row["confidence"],
        agreed=bool(row["agreed"]) if row["agreed"] is not None else None,
        note=row["note"],
        decided_at=datetime.fromisoformat(row["decided_at"]),
    )
