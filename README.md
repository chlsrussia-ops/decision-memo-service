# decision-memo-service

## Назначение
Сервис Human-in-the-Loop для принятия решений в e-commerce. Формирует
"decision memos" — структурированные записки для ручного ревью и
утверждения решений оператором.

## Стек
- Python, FastAPI
- PostgreSQL / SQLite
- Интеграция с decision-engine

## Место в экосистеме
Слой верификации решений оператором. Полная картина:
[chlsrussia-ops/content-factory-v4 → docs/ARCHITECTURE_MAP.md](https://github.com/chlsrussia-ops/content-factory-v4/blob/main/docs/ARCHITECTURE_MAP.md)

## Запуск
```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

## Статус
Активный.
