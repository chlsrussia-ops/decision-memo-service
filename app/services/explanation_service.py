"""Explanation Service — builds human-readable explanations.

v2: Rich template-based explanations with:
  - Context-aware summary based on all available data
  - Uncertainty markers when data is incomplete
  - Strength/weakness narrative
  - Actionable next-step suggestion
"""

from __future__ import annotations

from app.models.domain import UpstreamData
from app.schemas.decision import (
    MissingData,
    RecommendedAction,
    RedFlag,
    RiskFactor,
)


def build_summary(
    product_id: str,
    verdict: RecommendedAction,
    confidence: float,
    data: UpstreamData,
    red_flags: list[RedFlag],
    missing: list[MissingData],
) -> str:
    """Generate a rich human-readable summary."""

    pcs_str = f"PCS={data.pcs:.0f}" if data.pcs is not None else "PCS не рассчитан"
    parts: list[str] = []

    # ── Main verdict sentence ────────────────────────────────────────
    if verdict == RecommendedAction.BUY_CANDIDATE:
        parts.append(f"Продукт {product_id} — кандидат на закупку ({pcs_str}).")
        if confidence >= 0.7:
            parts.append("Данные уверенно подтверждают рекомендацию.")
        elif confidence >= 0.4:
            parts.append("Рекомендация умеренная — есть пробелы в данных.")
        else:
            parts.append("Уверенность низкая — перед решением проверьте недостающие данные.")

    elif verdict == RecommendedAction.WATCH:
        parts.append(f"Продукт {product_id} — в зоне наблюдения ({pcs_str}).")
        parts.append("Score недостаточен для закупки, но потенциал не исключён.")

    else:
        parts.append(f"Продукт {product_id} — не рекомендован ({pcs_str}).")
        if data.pcs is None:
            parts.append("Недостаточно данных для оценки.")
        else:
            parts.append("Текущие сигналы не поддерживают закупку.")

    # ── Strength context ─────────────────────────────────────────────
    strengths = []
    if data.tvs is not None and data.tvs >= 70:
        strengths.append(f"сильный тренд (TVS={data.tvs:.0f})")
    if data.pucs is not None and data.pucs >= 60:
        strengths.append(f"покупательная уверенность (PuCS={data.pucs:.0f})")
    if data.srs is not None and data.srs < 30:
        strengths.append(f"открытый рынок (SRS={data.srs:.0f})")
    if data.buy_intent_ratio is not None and data.buy_intent_ratio >= 0.05:
        strengths.append(f"buy intent {data.buy_intent_ratio:.0%}")

    if strengths and verdict in (RecommendedAction.BUY_CANDIDATE, RecommendedAction.WATCH):
        parts.append(f"Сильные стороны: {', '.join(strengths)}.")

    # ── Weakness context ─────────────────────────────────────────────
    weaknesses = []
    if data.srs is not None and data.srs > 60:
        weaknesses.append(f"перегретый рынок (SRS={data.srs:.0f})")
    if data.tvs is not None and data.tvs < 30:
        weaknesses.append(f"слабый тренд (TVS={data.tvs:.0f})")
    if data.buy_intent_ratio is not None and data.buy_intent_ratio < 0.02:
        weaknesses.append(f"низкий buy intent ({data.buy_intent_ratio:.1%})")

    if weaknesses:
        parts.append(f"Слабые стороны: {', '.join(weaknesses)}.")

    # ── Red flags ────────────────────────────────────────────────────
    if red_flags:
        critical = sum(1 for f in red_flags if f.severity == "critical")
        if critical > 0:
            parts.append(f"ВНИМАНИЕ: {critical} критических флага — доверие к score ограничено.")
        else:
            parts.append(f"Обнаружено {len(red_flags)} предупреждений.")

    # ── Uncertainty markers ──────────────────────────────────────────
    critical_missing = [m for m in missing if m.impact in ("critical", "high")]
    if critical_missing:
        fields = [m.field for m in critical_missing[:3]]
        parts.append(f"Неизвестно: {', '.join(fields)} — уверенность снижена.")

    # ── Data completeness ────────────────────────────────────────────
    available = sum(1 for v in [data.tvs, data.pucs, data.srs, data.otrs, data.pcs] if v is not None)
    if available < 3:
        parts.append("⚠ Менее 3 из 5 метрик доступно — memo неполный.")
    elif available == 5 and not missing:
        parts.append("Все метрики доступны — полная картина.")

    return " ".join(parts)


def build_next_action(
    verdict: RecommendedAction,
    confidence: float,
    red_flags: list[RedFlag],
    missing: list[MissingData],
    risks: list[RiskFactor],
) -> str:
    """Suggest a concrete next action for the human decision-maker."""
    if verdict == RecommendedAction.BUY_CANDIDATE:
        if confidence >= 0.7 and not red_flags:
            return "Рассмотрите закупку пробной партии. Все ключевые показатели положительны."
        elif red_flags:
            flags_str = "; ".join(f.message for f in red_flags[:2])
            return f"Перед закупкой разберитесь с флагами: {flags_str}"
        else:
            missing_str = ", ".join(m.field for m in missing[:3])
            return f"Рекомендация положительная, но дополните данные ({missing_str}) для уверенного решения."

    elif verdict == RecommendedAction.WATCH:
        if missing:
            return f"Дождитесь данных по: {', '.join(m.field for m in missing[:3])}. Пересмотрите через 3–7 дней."
        high_risks = [r for r in risks if r.level == "high"]
        if high_risks:
            return f"Наблюдайте за: {high_risks[0].factor}. Если ситуация улучшится — пересмотрите."
        return "Score в пограничной зоне. Подождите дополнительных сигналов перед решением."

    else:
        if not missing and confidence >= 0.5:
            return "Данных достаточно — продукт не проходит по текущим критериям. Переключитесь на другие кандидаты."
        elif missing:
            return "Отказ на основе неполных данных. Если есть основания пересмотреть — дополните метрики."
        return "Текущие сигналы отрицательные. Перейдите к следующему кандидату."
