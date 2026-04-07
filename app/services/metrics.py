"""Metrics — lightweight in-memory metrics for observability.

Tracks:
  - Total memos generated (by verdict)
  - Total human decisions (by action)
  - Average upstream latency
  - Error counts
  - LLM usage stats

No external dependency — simple counters exposed via /api/system/metrics.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Metrics:
    """Thread-safe metrics store."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # Memo generation
    memos_total: int = 0
    memos_buy: int = 0
    memos_watch: int = 0
    memos_reject: int = 0

    # Human decisions
    decisions_total: int = 0
    decisions_approve: int = 0
    decisions_watch: int = 0
    decisions_reject: int = 0
    decisions_agreed: int = 0
    decisions_disagreed: int = 0

    # Latency
    latency_sum_ms: int = 0
    latency_count: int = 0

    # LLM
    llm_calls: int = 0
    llm_successes: int = 0
    llm_failures: int = 0

    # Errors
    upstream_errors: int = 0

    # Start time
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def record_memo(self, verdict: str, latency_ms: int = 0):
        with self._lock:
            self.memos_total += 1
            if verdict == "BUY_CANDIDATE":
                self.memos_buy += 1
            elif verdict == "WATCH":
                self.memos_watch += 1
            else:
                self.memos_reject += 1
            if latency_ms:
                self.latency_sum_ms += latency_ms
                self.latency_count += 1

    def record_decision(self, action: str, agreed: bool | None = None):
        with self._lock:
            self.decisions_total += 1
            if action == "APPROVE":
                self.decisions_approve += 1
            elif action == "WATCH":
                self.decisions_watch += 1
            else:
                self.decisions_reject += 1
            if agreed is True:
                self.decisions_agreed += 1
            elif agreed is False:
                self.decisions_disagreed += 1

    def record_llm(self, success: bool):
        with self._lock:
            self.llm_calls += 1
            if success:
                self.llm_successes += 1
            else:
                self.llm_failures += 1

    def record_upstream_error(self):
        with self._lock:
            self.upstream_errors += 1

    def snapshot(self) -> dict:
        with self._lock:
            avg_latency = (
                round(self.latency_sum_ms / self.latency_count)
                if self.latency_count > 0
                else 0
            )
            return {
                "memos": {
                    "total": self.memos_total,
                    "buy_candidate": self.memos_buy,
                    "watch": self.memos_watch,
                    "reject": self.memos_reject,
                },
                "decisions": {
                    "total": self.decisions_total,
                    "approve": self.decisions_approve,
                    "watch": self.decisions_watch,
                    "reject": self.decisions_reject,
                    "agreed": self.decisions_agreed,
                    "disagreed": self.decisions_disagreed,
                    "agreement_rate": (
                        round(self.decisions_agreed / (self.decisions_agreed + self.decisions_disagreed), 2)
                        if (self.decisions_agreed + self.decisions_disagreed) > 0
                        else None
                    ),
                },
                "latency": {
                    "avg_ms": avg_latency,
                    "total_requests": self.latency_count,
                },
                "llm": {
                    "calls": self.llm_calls,
                    "successes": self.llm_successes,
                    "failures": self.llm_failures,
                    "success_rate": (
                        round(self.llm_successes / self.llm_calls, 2)
                        if self.llm_calls > 0
                        else None
                    ),
                },
                "errors": {
                    "upstream": self.upstream_errors,
                },
                "started_at": self.started_at,
            }


# Global singleton
metrics = Metrics()
