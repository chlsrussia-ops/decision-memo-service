# Decision Memo Service — Architecture

## Роль

Decision Memo Service — единая точка входа для формирования структурированной рекомендации по продукту. Система **НЕ принимает решений о закупке**. Она собирает evidence, применяет правила, объясняет причины и передаёт решение человеку.

## Принцип

```
Human decides. System recommends.
```

## Архитектурная позиция

Отдельный сервис (`decision-memo-service`), а не модуль внутри TCS.

Причины:
- Независимый lifecycle (деплой, версионирование правил)
- Чистая ответственность (orchestration + rules + explanation)
- Не зависит от БД других сервисов
- Может эволюционировать отдельно (LLM, caching, audit)

## Data Flow

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Scoring     │    │  Demand      │    │  TCS         │
│  Service     │    │  Layer       │    │  Analytics   │
│  :8005       │    │  :8090       │    │  :8400       │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                    ┌──────▼───────┐
                    │  Upstream    │
                    │  Clients     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Memo        │  ← orchestration
                    │  Service     │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──┐  ┌──────▼──┐  ┌─────▼────┐
       │  Rule   │  │  Risk   │  │ Explain  │
       │  Engine │  │  Service│  │ Service  │
       └─────────┘  └─────────┘  └──────────┘
                           │
                    ┌──────▼───────┐
                    │  Decision    │
                    │  Memo (JSON) │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──┐  ┌──────▼──┐  ┌─────▼────┐
       │Decision │  │ Explain │  │Dashboard │
       │  Card   │  │  Panel  │  │ Priority │
       └─────────┘  └─────────┘  └──────────┘
                           │
                    ┌──────▼───────┐
                    │  Human       │
                    │  Decision    │
                    └──────────────┘
```

## Компоненты

| Компонент | Файл | Роль |
|-----------|------|------|
| API Routes | `routes_decision_memo.py` | HTTP endpoints |
| Memo Service | `memo_service.py` | Orchestration — собирает данные, вызывает движки |
| Rule Engine | `rule_engine.py` | Verdict (BUY/WATCH/REJECT), confidence, red flags |
| Risk Service | `risk_service.py` | Оценка рисков (не red flags) |
| Explanation Service | `explanation_service.py` | Человекочитаемое summary |
| Upstream Clients | `upstream_clients.py` | Интеграция с внешними сервисами |

## Порт

`8600`

## Эволюция

| Версия | Что меняется |
|--------|-------------|
| v1 (текущая) | Rule-based, mock data |
| v2 | Real upstream integration |
| v3 | LLM-enhanced summary |
| v4 | Persistence, audit trail |
| v5 | Portfolio ranking, batch analysis |
