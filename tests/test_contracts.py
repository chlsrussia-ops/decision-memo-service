"""Contract tests — validate API response shapes match expected contracts.

These tests ensure the API doesn't break clients (UI, integrations)
by changing response format unexpectedly.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestMemoContract:
    """POST /api/decision-memo must always return these fields."""

    REQUIRED_FIELDS = {
        "product_id", "summary", "recommended_action", "confidence",
        "scores", "why_buy", "risks", "unknowns", "red_flags",
        "decision_factors", "human_required", "rule_engine_version",
        "generated_at",
    }

    SCORE_FIELDS = {"TVS", "PuCS", "SRS", "OTRS", "PCS"}

    def test_memo_has_all_required_fields(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        assert resp.status_code == 200
        data = resp.json()
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f"Missing fields: {missing}"

    def test_memo_scores_have_all_fields(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        data = resp.json()
        scores = data["scores"]
        missing = self.SCORE_FIELDS - set(scores.keys())
        assert not missing, f"Missing score fields: {missing}"

    def test_memo_action_is_valid_enum(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        data = resp.json()
        assert data["recommended_action"] in ("BUY_CANDIDATE", "WATCH", "REJECT")

    def test_memo_confidence_in_range(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        data = resp.json()
        assert 0.0 <= data["confidence"] <= 1.0

    def test_memo_human_required_always_true(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        data = resp.json()
        assert data["human_required"] is True

    def test_memo_lists_are_lists(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        data = resp.json()
        assert isinstance(data["why_buy"], list)
        assert isinstance(data["risks"], list)
        assert isinstance(data["unknowns"], list)
        assert isinstance(data["red_flags"], list)

    def test_memo_decision_factors_structure(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        data = resp.json()
        factors = data["decision_factors"]
        assert "primary" in factors
        assert isinstance(factors["primary"], str)

    def test_memo_has_next_action(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        data = resp.json()
        assert "next_action" in data

    def test_memo_has_data_completeness(self):
        resp = client.post("/api/decision-memo", json={"product_id": "PROD-001"})
        data = resp.json()
        assert "data_completeness" in data
        if data["data_completeness"] is not None:
            assert 0.0 <= data["data_completeness"] <= 1.0


class TestPrioritizedContract:
    """GET /api/products/prioritized must return ranked list."""

    def test_prioritized_has_products(self):
        resp = client.get("/api/products/prioritized")
        assert resp.status_code == 200
        data = resp.json()
        assert "products" in data
        assert "total" in data
        assert isinstance(data["products"], list)

    def test_prioritized_products_have_rank(self):
        resp = client.get("/api/products/prioritized")
        data = resp.json()
        for p in data["products"]:
            assert "rank" in p
            assert "product_id" in p
            assert "recommended_action" in p
            assert "confidence" in p

    def test_prioritized_ranks_are_sequential(self):
        resp = client.get("/api/products/prioritized")
        data = resp.json()
        ranks = [p["rank"] for p in data["products"]]
        assert ranks == list(range(1, len(ranks) + 1))


class TestHumanDecisionContract:
    """POST /api/human-decision must return stored decision."""

    def test_decision_returns_id(self):
        resp = client.post("/api/human-decision", json={
            "product_id": "TEST-CONTRACT",
            "action": "APPROVE",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["product_id"] == "TEST-CONTRACT"
        assert data["action"] == "APPROVE"
        assert "decided_at" in data

    def test_decision_tracks_agreement(self):
        resp = client.post("/api/human-decision", json={
            "product_id": "PROD-001",
            "action": "APPROVE",
        })
        data = resp.json()
        assert "agreed_with_system" in data


class TestAuditTrailContract:
    """GET /api/audit-trail must return entries with agreement rate."""

    def test_audit_trail_structure(self):
        resp = client.get("/api/audit-trail")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert "agreement_rate" in data

    def test_audit_entries_have_fields(self):
        # Create a decision first
        client.post("/api/human-decision", json={
            "product_id": "AUDIT-TEST",
            "action": "WATCH",
        })
        resp = client.get("/api/audit-trail")
        data = resp.json()
        if data["entries"]:
            entry = data["entries"][0]
            assert "id" in entry
            assert "product_id" in entry
            assert "human_action" in entry
            assert "decided_at" in entry


class TestHealthContract:
    """GET /api/system/decision-health must return status + upstreams."""

    def test_health_structure(self):
        resp = client.get("/api/system/decision-health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded", "unhealthy")
        assert "upstreams" in data
        assert "rule_engine_version" in data


class TestMetricsContract:
    """GET /api/system/metrics must return counters."""

    def test_metrics_structure(self):
        resp = client.get("/api/system/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "memos" in data
        assert "decisions" in data
        assert "latency" in data
        assert "cache" in data


class TestRulesContract:
    """GET /api/system/rules must return current rules + history."""

    def test_rules_structure(self):
        resp = client.get("/api/system/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "current" in data
        assert "history" in data
        assert "thresholds" in data["current"]
        assert "red_flags" in data["current"]
        assert "verdict_rules" in data["current"]
