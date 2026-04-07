"""Memo Cache — in-memory TTL cache for decision memos.

Avoids redundant upstream calls for the same product within TTL window.
Cache is invalidated on force_refresh=True.

Default TTL: 5 minutes (memos don't change rapidly).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from app.schemas.decision import DecisionMemo

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300  # 5 minutes

_cache: dict[str, tuple[DecisionMemo, float]] = {}


def get(product_id: str) -> Optional[DecisionMemo]:
    """Get cached memo if exists and not expired."""
    entry = _cache.get(product_id)
    if entry is None:
        return None

    memo, expires_at = entry
    if time.monotonic() > expires_at:
        del _cache[product_id]
        logger.debug("Cache expired for %s", product_id)
        return None

    logger.debug("Cache hit for %s", product_id)
    return memo


def put(product_id: str, memo: DecisionMemo, ttl: int = DEFAULT_TTL):
    """Store memo in cache."""
    _cache[product_id] = (memo, time.monotonic() + ttl)
    logger.debug("Cached memo for %s (ttl=%ds)", product_id, ttl)


def invalidate(product_id: str):
    """Remove a specific product from cache."""
    _cache.pop(product_id, None)


def clear():
    """Clear entire cache."""
    _cache.clear()


def stats() -> dict:
    """Return cache statistics."""
    now = time.monotonic()
    valid = sum(1 for _, (_, exp) in _cache.items() if exp > now)
    expired = len(_cache) - valid
    return {
        "entries": len(_cache),
        "valid": valid,
        "expired": expired,
    }
