# Domain Model

## Сущности

### ScoreSnapshot
Срез всех scoring-метрик на момент времени.

| Поле | Тип | Описание |
|------|-----|----------|
| TVS | float? | Trend Velocity Score 0-100 |
| PuCS | float? | Purchase Confidence Score 0-100 |
| SRS | float? | Supply/Risk Saturation Score 0-100 |
| OTRS | float? | Organic Traffic Relevance Score 0-100 |
| PCS | float? | Product Composite Score 0-100 |
| scored_at | datetime? | Когда рассчитан |

### DemandSnapshot
Сигналы спроса.

| Поле | Тип | Описание |
|------|-----|----------|
| search_volume | int? | Объём поиска |
| search_trend | string? | rising / stable / falling |
| buy_intent_ratio | float? | Доля покупательского намерения 0.0–1.0 |
| source_count | int? | Количество источников |
| platform_count | int? | Количество платформ |

### RedFlag
Условие, которое **переопределяет доверие** к score.

| Код | Условие | Severity |
|-----|---------|----------|
| OTRS_NULL | OTRS отсутствует | high |
| LOW_BUY_INTENT | buy_intent < 2% | high |
| SINGLE_SOURCE | source_count = 1 | critical |
| MARKET_OVERHEATED | SRS > 60 | high |

### RiskFactor
Риск — фактор для рассмотрения при принятии решения.

| Поле | Тип | Описание |
|------|-----|----------|
| factor | string | Название риска |
| level | string | low / medium / high |
| description | string | Подробное описание |

### MissingData
Отсутствующие данные, снижающие confidence.

| Поле | Тип | Описание |
|------|-----|----------|
| field | string | Название поля |
| impact | string | low / medium / high / critical |
| description | string | Что означает отсутствие |

### DecisionMemo
Основной выход системы — полный brief для человека.

| Поле | Тип | Описание |
|------|-----|----------|
| product_id | string | ID продукта |
| summary | string | 1-2 предложения для человека |
| recommended_action | enum | BUY_CANDIDATE / WATCH / REJECT |
| confidence | float | 0.0–1.0 |
| scores | ScoreSnapshot | Все метрики |
| demand | DemandSnapshot? | Спрос |
| why_buy | string[] | Причины "за" |
| risks | RiskFactor[] | Риски |
| unknowns | MissingData[] | Что не хватает |
| red_flags | RedFlag[] | Красные флаги |
| decision_factors | {primary, secondary} | Главные факторы |
| human_required | bool | ВСЕГДА true |

### HumanDecision
Решение человека — **отдельная сущность**, не часть memo.

| Поле | Тип | Описание |
|------|-----|----------|
| product_id | string | ID продукта |
| action | enum | APPROVE / REJECT / WATCH |
| note | string? | Причина, особенно если не согласен |
| decided_at | datetime | Когда принято |
