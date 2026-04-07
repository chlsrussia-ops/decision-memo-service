"""Risk Service — builds structured risk factors from upstream data.

Risks are NOT the same as red flags:
- Red flags = hard overrides that reduce trust in score
- Risks = factors to consider in the decision, graded by severity
"""

from __future__ import annotations

from app.models.domain import UpstreamData
from app.schemas.decision import RiskFactor

# Thresholds
SRS_HIGH = 60
SRS_MEDIUM = 40
TVS_LOW = 30
SEARCH_VOLUME_LOW = 1000


def assess_risks(data: UpstreamData) -> list[RiskFactor]:
    """Assess risk factors from upstream data."""
    risks: list[RiskFactor] = []

    # Market saturation risk
    if data.srs is not None:
        if data.srs > SRS_HIGH:
            risks.append(RiskFactor(
                factor="Насыщение рынка",
                level="high",
                description=f"SRS={data.srs:.0f} — рынок перегрет. "
                            "Высокая конкуренция, сложно занять долю, маржа под давлением.",
            ))
        elif data.srs > SRS_MEDIUM:
            risks.append(RiskFactor(
                factor="Умеренная конкуренция",
                level="medium",
                description=f"SRS={data.srs:.0f} — рынок конкурентный. "
                            "Потребуется стратегия дифференциации.",
            ))

    # Weak trend
    if data.tvs is not None and data.tvs < TVS_LOW:
        risks.append(RiskFactor(
            factor="Слабый тренд",
            level="medium",
            description=f"TVS={data.tvs:.0f} — тренд слабый или угасающий. "
                        "Спрос может не вырасти.",
        ))

    # Falling search trend
    if data.search_trend == "falling":
        risks.append(RiskFactor(
            factor="Падающий поисковый тренд",
            level="high",
            description="Поисковый тренд снижается — спрос может продолжить падение.",
        ))

    # Low search volume
    if data.search_volume is not None and data.search_volume < SEARCH_VOLUME_LOW:
        risks.append(RiskFactor(
            factor="Низкий объём поиска",
            level="medium",
            description=f"Объём поиска {data.search_volume:,} — рынок узкий, потенциал ограничен.",
        ))

    # Low buy intent
    if data.buy_intent_ratio is not None and data.buy_intent_ratio < 0.03:
        risks.append(RiskFactor(
            factor="Низкий buy intent",
            level="high",
            description=f"Buy intent {data.buy_intent_ratio:.1%} — "
                        "люди ищут, но не покупают.",
        ))

    # Single platform dependency
    if data.platform_count is not None and data.platform_count <= 1:
        risks.append(RiskFactor(
            factor="Зависимость от одной платформы",
            level="medium",
            description="Сигналы только с одной платформы — высокая зависимость.",
        ))

    # Upstream failures
    if data.errors:
        risks.append(RiskFactor(
            factor="Неполные данные",
            level="medium",
            description=f"Ошибки при сборе данных: {'; '.join(data.errors[:3])}. "
                        "Memo может быть неполным.",
        ))

    return risks
