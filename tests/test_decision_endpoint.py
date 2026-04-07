"""Tests for API endpoints — integration tests with mock data."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_basic_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_root(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "principle" in data


class TestDecisionMemoEndpoint:
    def test_create_memo_buy_candidate(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["product_id"] == "PROD-001"
        assert data["recommended_action"] == "BUY_CANDIDATE"
        assert data["human_required"] is True
        assert data["confidence"] > 0
        assert "summary" in data
        assert "scores" in data
        assert "why_buy" in data
        assert "risks" in data
        assert "red_flags" in data
        assert "unknowns" in data
        assert "decision_factors" in data

    def test_create_memo_watch(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-002"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_action"] == "WATCH"
        assert data["human_required"] is True

    def test_create_memo_reject(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-003"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_action"] == "REJECT"
        assert data["human_required"] is True
        assert len(data["red_flags"]) >= 2

    def test_create_memo_no_data(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-006"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_action"] == "REJECT"
        assert data["confidence"] <= 0.15

    def test_create_memo_unknown_product(self):
        resp = client.post("/api/decision-memo", json={"product_id": "NONEXISTENT"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_action"] == "REJECT"

    def test_create_memo_empty_product_id(self):
        resp = client.post("/api/decision-memo", json={"product_id": ""})
        assert resp.status_code == 422

    def test_get_memo(self):
        resp = client.get("/api/decision-memo/PROD-005")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_action"] == "BUY_CANDIDATE"
        assert data["confidence"] >= 0.7


class TestPrioritizedEndpoint:
    def test_prioritized_list(self):
        resp = client.get("/api/products/prioritized")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] >= 1
        assert len(data["products"]) >= 1

        # First product should be BUY_CANDIDATE
        first = data["products"][0]
        assert first["recommended_action"] == "BUY_CANDIDATE"
        assert first["rank"] == 1

    def test_prioritized_ranking_order(self):
        resp = client.get("/api/products/prioritized")
        data = resp.json()

        actions = [p["recommended_action"] for p in data["products"]]
        # All BUY_CANDIDATE should come before WATCH, before REJECT
        buy_indices = [i for i, a in enumerate(actions) if a == "BUY_CANDIDATE"]
        watch_indices = [i for i, a in enumerate(actions) if a == "WATCH"]
        reject_indices = [i for i, a in enumerate(actions) if a == "REJECT"]

        if buy_indices and watch_indices:
            assert max(buy_indices) < min(watch_indices)
        if watch_indices and reject_indices:
            assert max(watch_indices) < min(reject_indices)


class TestHumanDecisionEndpoint:
    def test_record_decision(self):
        resp = client.post("/api/human-decision", json={
            "product_id": "PROD-001",
            "action": "APPROVE",
            "note": "Согласен с рекомендацией, закупаю пробную партию",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["product_id"] == "PROD-001"
        assert data["action"] == "APPROVE"
        assert data["note"] is not None

    def test_record_rejection(self):
        resp = client.post("/api/human-decision", json={
            "product_id": "PROD-001",
            "action": "REJECT",
            "note": "Не согласен — уже работаю с этим поставщиком",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "REJECT"


class TestSystemHealthEndpoint:
    def test_health_check(self):
        resp = client.get("/api/system/decision-health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "upstreams" in data
        assert "rule_engine_version" in data
