"""Explanation Service — builds human-readable summary from evaluation results.

v1: template-based, no LLM.
v2 (future): LLM-enhanced summary with rule-based fallback.
"""

from __future__ import annotations

from app.models.domain import UpstreamData
from app.schemas.decision import (
    MissingData,
    RecommendedAction,
    RedFlag,
)


def build_summary(
    product_id: str,
    verdict: RecommendedAction,
    confidence: float,
    data: UpstreamData,
    red_flags: list[RedFlag],
    missing: list[MissingData],
) -> str:
    """Generate a human-readable 1-2 sentence summary of the decision memo."""

    pcs_str = f"PCS={data.pcs:.0f}" if data.pcs is not None else "PCS не рассчитан"

    if verdict == RecommendedAction.BUY_CANDIDATE:
        base = f"Продукт {product_id} — кандидат на закупку ({pcs_str})."
        if confidence >= 0.7:
            qualifier = " Данные подтверждают рекомендацию с высокой уверенностью."
        elif confidence >= 0.4:
            qualifier = " Рекомендация умеренно уверенная — есть пробелы в данных."
        else:
            qualifier = " Уверенность низкая — требуется дополнительная проверка."

    elif verdict == RecommendedAction.WATCH:
        base = f"Продукт {product_id} — в зоне наблюдения ({pcs_str})."
        qualifier = " Score недостаточен для рекомендации закупки, но не исключает потенциал."

    else:
        base = f"Продукт {product_id} — не рекомендован ({pcs_str})."
        if data.pcs is None:
            qualifier = " Недостаточно данных для оценки."
        else:
            qualifier = " Score ниже порога, текущие сигналы не поддерживают закупку."

    # Append red flag warning
    if red_flags:
        flag_count = len(red_flags)
        critical = sum(1 for f in red_flags if f.severity == "critical")
        if critical > 0:
            base += f" ВНИМАНИЕ: {critical} критических флага из {flag_count}."
        else:
            base += f" Обнаружено {flag_count} предупреждений."

    # Append missing data note
    critical_missing = [m for m in missing if m.impact in ("critical", "high")]
    if critical_missing:
        base += f" Не хватает {len(critical_missing)} важных показателей."

    return base + qualifier
