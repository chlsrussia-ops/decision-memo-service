"""LLM Summary Service — enhances memo summary using Claude API.

Rules:
  - LLM generates ONLY the summary text, NOT the verdict
  - Verdict, confidence, red_flags are ALWAYS from rule engine
  - If LLM is unavailable, falls back to template-based summary
  - LLM output is constrained to 2-3 sentences in Russian
  - No auto-buy language allowed in output
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings
from app.schemas.decision import (
    DecisionMemo,
    MissingData,
    RecommendedAction,
    RedFlag,
    RiskFactor,
)

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 250


async def enhance_summary(memo: DecisionMemo) -> Optional[str]:
    """Generate an LLM-enhanced summary for a decision memo.

    Returns enhanced summary string, or None if LLM unavailable.
    The verdict and all scores remain from the rule engine.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.debug("No ANTHROPIC_API_KEY configured, skipping LLM enhancement")
        return None

    prompt = _build_prompt(memo)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": MODEL,
                    "max_tokens": MAX_TOKENS,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

        if resp.status_code != 200:
            logger.warning("LLM API returned %d: %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        content = data.get("content", [])
        if content and content[0].get("type") == "text":
            summary = content[0]["text"].strip()
            # Guard: reject if LLM tries to override verdict
            if _contains_forbidden(summary):
                logger.warning("LLM output contained forbidden language, using template")
                return None
            return summary

        return None

    except Exception as e:
        logger.warning("LLM enhancement failed: %s", e)
        return None


def _build_prompt(memo: DecisionMemo) -> str:
    """Build a constrained prompt for summary generation."""
    scores = []
    if memo.scores.PCS is not None:
        scores.append(f"PCS={memo.scores.PCS:.0f}")
    if memo.scores.TVS is not None:
        scores.append(f"TVS={memo.scores.TVS:.0f}")
    if memo.scores.PuCS is not None:
        scores.append(f"PuCS={memo.scores.PuCS:.0f}")
    if memo.scores.SRS is not None:
        scores.append(f"SRS={memo.scores.SRS:.0f}")
    if memo.scores.OTRS is not None:
        scores.append(f"OTRS={memo.scores.OTRS:.0f}")

    scores_str = ", ".join(scores) if scores else "нет данных"

    flags_str = "; ".join(f.message for f in memo.red_flags) if memo.red_flags else "нет"
    risks_str = "; ".join(f"{r.factor} ({r.level})" for r in memo.risks[:3]) if memo.risks else "нет"
    why_str = "; ".join(memo.why_buy[:3]) if memo.why_buy else "нет"
    unknowns_str = "; ".join(u.field for u in memo.unknowns[:3]) if memo.unknowns else "нет"

    return f"""Ты — аналитик e-commerce. Напиши краткое резюме (2-3 предложения) на русском для лица, принимающего решение о закупке.

Продукт: {memo.product_id}
Рекомендация системы: {memo.recommended_action.value}
Уверенность: {memo.confidence:.0%}
Scores: {scores_str}
Причины "за": {why_str}
Красные флаги: {flags_str}
Риски: {risks_str}
Недостающие данные: {unknowns_str}
Полнота данных: {memo.data_completeness or 0:.0%}

ПРАВИЛА:
- Пиши 2-3 коротких предложения
- Объясни ПОЧЕМУ рекомендация именно такая
- Укажи главный риск или неизвестность
- НЕ используй слова "закупить", "купить", "заказать" как призыв к действию
- НЕ принимай решение за человека
- Если данных мало — честно скажи об этом"""


def _contains_forbidden(text: str) -> bool:
    """Check if LLM output contains forbidden auto-buy language."""
    forbidden = [
        "необходимо закупить",
        "нужно купить",
        "рекомендую купить",
        "следует закупить",
        "закупайте",
        "покупайте",
        "оформите заказ",
    ]
    lower = text.lower()
    return any(phrase in lower for phrase in forbidden)
