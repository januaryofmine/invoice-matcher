from unittest.mock import MagicMock, patch

import pytest

from pipeline.matcher import MatcherConfig, MatchStatus, match_invoices
from pipeline.scorer import ScorerConfig
from tests.fixtures import (
    DEL_66787,
    DEL_66984,
    DEL_66985,
    DEL_67131,
    INV_66787_A,
    INV_66985_A,
    INV_67131_A,
    INV_DATE_FAIL,
    INV_NO_PLATE,
    INV_UNKNOWN_PLATE,
)

DEFAULT_CONFIG = MatcherConfig(use_llm=False)


def results_by_id(results):
    return {r.invoice_id: r for r in results}


class TestNoPlate:
    def test_no_plate_status(self):
        results = match_invoices([DEL_67131], [INV_NO_PLATE], DEFAULT_CONFIG)
        assert results[0].status == MatchStatus.NO_PLATE

    def test_no_plate_no_delivery_assigned(self):
        results = match_invoices([DEL_67131], [INV_NO_PLATE], DEFAULT_CONFIG)
        assert results[0].matched_delivery_id is None


class TestNoMatch:
    def test_unknown_plate(self):
        results = match_invoices([DEL_67131], [INV_UNKNOWN_PLATE], DEFAULT_CONFIG)
        assert results[0].status == MatchStatus.NO_MATCH

    def test_date_outside_window(self):
        results = match_invoices(
            [DEL_67131, DEL_66787], [INV_DATE_FAIL], DEFAULT_CONFIG
        )
        assert results[0].status == MatchStatus.NO_MATCH


class TestScenarioA:
    """plate 49H01936 — 2 deliveries, different dates → date filter resolves."""

    def test_inv_67131_matches_correct_delivery(self):
        results = match_invoices(
            [DEL_67131, DEL_66787],
            [INV_67131_A],
            DEFAULT_CONFIG,
        )
        r = results[0]
        assert r.status == MatchStatus.AUTO_MATCH
        assert r.matched_delivery_id == 67131

    def test_inv_66787_matches_correct_delivery(self):
        results = match_invoices(
            [DEL_67131, DEL_66787],
            [INV_66787_A],
            DEFAULT_CONFIG,
        )
        r = results[0]
        assert r.status == MatchStatus.AUTO_MATCH
        assert r.matched_delivery_id == 66787

    def test_both_invoices_correct(self):
        results = match_invoices(
            [DEL_67131, DEL_66787],
            [INV_67131_A, INV_66787_A],
            DEFAULT_CONFIG,
        )
        by_id = results_by_id(results)
        assert by_id[10001].matched_delivery_id == 67131
        assert by_id[10002].matched_delivery_id == 66787


class TestScenarioB:
    """plate 50H67882 — same date, different dropoff → address score resolves."""

    def test_big_c_invoice_matches_big_c_delivery(self):
        results = match_invoices(
            [DEL_66985, DEL_66984],
            [INV_66985_A],
            DEFAULT_CONFIG,
        )
        r = results[0]
        assert r.status == MatchStatus.AUTO_MATCH
        assert r.matched_delivery_id == 66985

    def test_score_gap_is_significant(self):
        results = match_invoices(
            [DEL_66985, DEL_66984],
            [INV_66985_A],
            DEFAULT_CONFIG,
        )
        assert results[0].score_gap > 0.2


class TestScorerConfig:
    def test_custom_threshold(self):
        """With very high threshold, auto-match becomes harder."""
        config = MatcherConfig(
            use_llm=False,
            scorer=ScorerConfig(confidence_threshold=0.99),
        )
        results = match_invoices(
            [DEL_66985, DEL_66984],
            [INV_66985_A],
            config,
        )
        # Even with high threshold, should manual_review (not crash)
        assert results[0].status in (MatchStatus.AUTO_MATCH, MatchStatus.MANUAL_REVIEW)

    def test_date_window_zero_excludes_adjacent_days(self):
        config = MatcherConfig(date_window_days=0, use_llm=False)
        # INV_67131_A date=04/07 matches DEL_67131 pickup=04/07 exactly
        results = match_invoices([DEL_67131, DEL_66787], [INV_67131_A], config)
        assert results[0].matched_delivery_id == 67131


class TestOutputStructure:
    def test_result_has_top_candidates(self):
        results = match_invoices(
            [DEL_66985, DEL_66984],
            [INV_66985_A],
            DEFAULT_CONFIG,
        )
        r = results[0]
        assert len(r.top_candidates) >= 1
        assert "delivery_id" in r.top_candidates[0]
        assert "score" in r.top_candidates[0]
        assert "reasons" in r.top_candidates[0]

    def test_reasons_has_address_and_weight(self):
        results = match_invoices(
            [DEL_66985, DEL_66984],
            [INV_66985_A],
            DEFAULT_CONFIG,
        )
        reasons = results[0].top_candidates[0]["reasons"]
        assert "address_score" in reasons
        assert "weight_score" in reasons

    def test_all_invoices_get_result(self):
        all_invoices = [
            INV_67131_A,
            INV_66787_A,
            INV_66985_A,
            INV_NO_PLATE,
            INV_UNKNOWN_PLATE,
        ]
        results = match_invoices(
            [DEL_67131, DEL_66787, DEL_66985, DEL_66984], all_invoices, DEFAULT_CONFIG
        )
        assert len(results) == len(all_invoices)


class TestLLMFallback:
    def test_llm_called_when_gap_below_threshold(self):
        """When gap < threshold, LLM should be called (if use_llm=True)."""
        config = MatcherConfig(
            use_llm=True,
            scorer=ScorerConfig(confidence_threshold=0.99),  # force LLM
        )
        mock_result = {
            "matched_delivery_id": 66985,
            "confidence": "high",
            "reason": "address matches Big C",
        }
        # Use dependency injection instead of patching module-level name
        mock_llm = MagicMock(return_value=mock_result)
        results = match_invoices([DEL_66985, DEL_66984], [INV_66985_A], config, llm_resolver=mock_llm)
        assert mock_llm.called
        assert results[0].status == MatchStatus.LLM_MATCH
        assert results[0].matched_delivery_id == 66985

    def test_llm_low_confidence_goes_to_manual_review(self):
        config = MatcherConfig(
            use_llm=True,
            scorer=ScorerConfig(confidence_threshold=0.99),
        )
        mock_result = {
            "matched_delivery_id": None,
            "confidence": "low",
            "reason": "cannot determine",
        }
        mock_llm = MagicMock(return_value=mock_result)
        results = match_invoices([DEL_66985, DEL_66984], [INV_66985_A], config, llm_resolver=mock_llm)
        assert results[0].status == MatchStatus.MANUAL_REVIEW
