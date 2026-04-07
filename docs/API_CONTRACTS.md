# API Contracts

Base URL: `http://server:8600`

## POST /api/decision-memo

Сгенерировать Decision Memo для продукта.

### Request
```json
{
  "product_id": "PROD-001",
  "force_refresh": false
}
```

### Response 200
```json
{
  "product_id": "PROD-001",
  "summary": "Продукт PROD-001 — кандидат на закупку (PCS=81). Данные подтверждают рекомендацию с высокой уверенностью.",
  "recommended_action": "BUY_CANDIDATE",
  "confidence": 0.87,
  "scores": {
    "TVS": 78, "PuCS": 82, "SRS": 25, "OTRS": 65, "PCS": 81,
    "scored_at": "2026-04-07T12:00:00Z"
  },
  "demand": {
    "search_volume": 12000,
    "search_trend": "rising",
    "buy_intent_ratio": 0.08,
    "source_count": 4,
    "platform_count": 3,
    "category": "electronics",
    "region": "RU"
  },
  "why_buy": [
    "Композитный score PCS=81 — выше порога закупки",
    "Сильный тренд: TVS=78",
    "Высокая покупательная уверенность: PuCS=82",
    "Хороший buy intent: 8.0%",
    "Высокий объём поиска: 12,000",
    "Низкая конкуренция: SRS=25",
    "Кросс-валидация: 4 источников"
  ],
  "risks": [],
  "unknowns": [],
  "red_flags": [],
  "decision_factors": {
    "primary": "PCS=81 выше порога 75",
    "secondary": "сильный тренд (TVS=78); высокая покупательная уверенность (PuCS=82); buy intent 8.0%"
  },
  "human_required": true,
  "rule_engine_version": "1.0.0",
  "generated_at": "2026-04-07T12:00:00Z",
  "upstream_latency_ms": 5
}
```

### Response 422 — Validation Error
```json
{
  "detail": [{"loc": ["body", "product_id"], "msg": "...", "type": "..."}]
}
```

---

## GET /api/decision-memo/{product_id}

Получить memo (Phase 1: генерирует на лету).

### Response 200
Тот же формат, что POST.

---

## POST /api/human-decision

Записать решение человека.

### Request
```json
{
  "product_id": "PROD-001",
  "action": "APPROVE",
  "note": "Согласен, закупаю пробную партию"
}
```

### Response 200
```json
{
  "id": "uuid",
  "product_id": "PROD-001",
  "action": "APPROVE",
  "note": "Согласен, закупаю пробную партию",
  "decided_at": "2026-04-07T12:05:00Z",
  "memo_snapshot": null
}
```

---

## GET /api/products/prioritized

Приоритизированный список для разбора.

### Response 200
```json
{
  "products": [
    {
      "product_id": "PROD-005",
      "recommended_action": "BUY_CANDIDATE",
      "confidence": 0.92,
      "pcs": 89,
      "red_flag_count": 0,
      "missing_data_count": 0,
      "summary": "...",
      "rank": 1
    }
  ],
  "total": 8,
  "generated_at": "2026-04-07T12:00:00Z"
}
```

---

## GET /api/system/decision-health

Здоровье системы и upstream.

### Response 200
```json
{
  "status": "degraded",
  "version": "1.0.0",
  "rule_engine_version": "1.0.0",
  "upstreams": [
    {"name": "scoring-service", "healthy": true, "latency_ms": 45},
    {"name": "demand-layer", "healthy": false, "error": "Connection refused"}
  ],
  "checked_at": "2026-04-07T12:00:00Z"
}
```

---

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK |
| 422 | Validation error (empty product_id, etc.) |
| 500 | Internal error (upstream failure, etc.) |
