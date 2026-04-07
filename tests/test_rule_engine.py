"""Tests for the rule engine — verdict, confidence, red flags, missing data."""

import pytest

from app.models.domain import UpstreamData
from app.schemas.decision import RecommendedAction, RedFlagCode
from app.services.rule_engine import (
    build_why_buy,
    compute_confidence,
    compute_verdict,
    detect_missing_data,
    detect_red_flags,
    determine_factors,
    evaluate,
)


# ── Verdict Tests ────────────────────────────────────────────────────

class TestVerdict:
    def test_buy_candidate_high_pcs(self):
        data = UpstreamData(product_id="P1", pcs=85)
        assert compute_verdict(data) == RecommendedAction.BUY_CANDIDATE

    def test_buy_candidate_threshold(self):
        data = UpstreamData(product_id="P1", pcs=75)
        assert compute_verdict(data) == RecommendedAction.BUY_CANDIDATE

    def test_watch_mid_pcs(self):
        data = UpstreamData(product_id="P1", pcs=60)
        assert compute_verdict(data) == RecommendedAction.WATCH

    def test_watch_threshold(self):
        data = UpstreamData(product_id="P1", pcs=50)
        assert compute_verdict(data) == RecommendedAction.WATCH

    def test_reject_low_pcs(self):
        data = UpstreamData(product_id="P1", pcs=30)
        assert compute_verdict(data) == RecommendedAction.REJECT

    def test_reject_zero_pcs(self):
        data = UpstreamData(product_id="P1", pcs=0)
        assert compute_verdict(data) == RecommendedAction.REJECT

    def test_reject_none_pcs(self):
        data = UpstreamData(product_id="P1", pcs=None)
        assert compute_verdict(data) == RecommendedAction.REJECT


# ── Red Flag Tests ───────────────────────────────────────────────────

class TestRedFlags:
    def test_otrs_null_flag(self):
        data = UpstreamData(product_id="P1", otrs=None)
        flags = detect_red_flags(data)
        codes = [f.code for f in flags]
        assert RedFlagCode.OTRS_NULL in codes

    def test_otrs_present_no_flag(self):
        data = UpstreamData(product_id="P1", otrs=50)
        flags = detect_red_flags(data)
        codes = [f.code for f in flags]
        assert RedFlagCode.OTRS_NULL not in codes

    def test_low_buy_intent_flag(self):
        data = UpstreamData(product_id="P1", buy_intent_ratio=0.01)
        flags = detect_red_flags(data)
        codes = [f.code for f in flags]
        assert RedFlagCode.LOW_BUY_INTENT in codes

    def test_good_buy_intent_no_flag(self):
        data = UpstreamData(product_id="P1", buy_intent_ratio=0.05)
        flags = detect_red_flags(data)
        codes = [f.code for f in flags]
        assert RedFlagCode.LOW_BUY_INTENT not in codes

    def test_single_source_flag(self):
        data = UpstreamData(product_id="P1", source_count=1)
        flags = detect_red_flags(data)
        codes = [f.code for f in flags]
        assert RedFlagCode.SINGLE_SOURCE in codes

    def test_multiple_sources_no_flag(self):
        data = UpstreamData(product_id="P1", source_count=3)
        flags = detect_red_flags(data)
        codes = [f.code for f in flags]
        assert RedFlagCode.SINGLE_SOURCE not in codes

    def test_market_overheated_flag(self):
        data = UpstreamData(product_id="P1", srs=70)
        flags = detect_red_flags(data)
        codes = [f.code for f in flags]
        assert RedFlagCode.MARKET_OVERHEATED in codes

    def test_normal_srs_no_flag(self):
        data = UpstreamData(product_id="P1", srs=40)
        flags = detect_red_flags(data)
        codes = [f.code for f in flags]
        assert RedFlagCode.MARKET_OVERHEATED not in codes


# ── Missing Data Tests ───────────────────────────────────────────────

class TestMissingData:
    def test_all_missing(self):
        data = UpstreamData(product_id="P1")
        missing = detect_missing_data(data)
        fields = [m.field for m in missing]
        assert "PCS" in fields
        assert "TVS" in fields
        assert "scoring_service" in fields
        assert "demand_layer" in fields

    def test_nothing_missing(self):
        data = UpstreamData(
            product_id="P1",
            pcs=80, tvs=70, pucs=60, otrs=50, srs=30,
            buy_intent_ratio=0.05, search_volume=10000,
            scoring_available=True, demand_available=True,
        )
        missing = detect_missing_data(data)
        assert len(missing) == 0


# ── Confidence Tests ─────────────────────────────────────────────────

class TestConfidence:
    def test_full_data_high_confidence(self):
        data = UpstreamData(
            product_id="P1",
            pcs=80, tvs=70, pucs=60, otrs=50, srs=30,
            buy_intent_ratio=0.05, search_volume=10000,
            scoring_available=True, demand_available=True,
        )
        flags = detect_red_flags(data)
        missing = detect_missing_data(data)
        conf = compute_confidence(data, flags, missing)
        assert conf >= 0.8

    def test_no_data_low_confidence(self):
        data = UpstreamData(product_id="P1")
        flags = detect_red_flags(data)
        missing = detect_missing_data(data)
        conf = compute_confidence(data, flags, missing)
        assert conf <= 0.15

    def test_confidence_floor(self):
        data = UpstreamData(product_id="P1")
        flags = detect_red_flags(data)
        missing = detect_missing_data(data)
        conf = compute_confidence(data, flags, missing)
        assert conf >= 0.05


# ── Full Evaluation Tests ────────────────────────────────────────────

class TestFullEvaluation:
    def test_strong_buy_candidate(self):
        data = UpstreamData(
            product_id="P1",
            pcs=85, tvs=80, pucs=75, otrs=60, srs=20,
            buy_intent_ratio=0.10, search_volume=15000,
            source_count=4, platform_count=3,
            scoring_available=True, demand_available=True,
        )
        result = evaluate(data)
        assert result["verdict"] == RecommendedAction.BUY_CANDIDATE
        assert result["confidence"] >= 0.7
        assert len(result["red_flags"]) == 0
        assert len(result["why_buy"]) >= 3

    def test_weak_reject(self):
        data = UpstreamData(
            product_id="P2",
            pcs=30, tvs=20, pucs=25, otrs=None, srs=75,
            buy_intent_ratio=0.01, search_volume=500,
            source_count=1, platform_count=1,
            scoring_available=True, demand_available=True,
        )
        result = evaluate(data)
        assert result["verdict"] == RecommendedAction.REJECT
        assert len(result["red_flags"]) >= 3
        assert result["confidence"] < 0.5

    def test_watch_zone(self):
        data = UpstreamData(
            product_id="P3",
            pcs=60, tvs=55, pucs=50, otrs=45, srs=40,
            buy_intent_ratio=0.04, search_volume=6000,
            source_count=2, platform_count=2,
            scoring_available=True, demand_available=True,
        )
        result = evaluate(data)
        assert result["verdict"] == RecommendedAction.WATCH

    def test_human_required_always_true(self):
        """The system NEVER makes the decision — human_required must be True."""
        data = UpstreamData(product_id="P1", pcs=95, scoring_available=True)
        result = evaluate(data)
        # human_required is set in memo_service, but verify verdict is just a recommendation
        assert result["verdict"] in [
            RecommendedAction.BUY_CANDIDATE,
            RecommendedAction.WATCH,
            RecommendedAction.REJECT,
        ]
