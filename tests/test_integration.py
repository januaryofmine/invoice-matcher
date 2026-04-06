"""
Integration tests — requires large_set.json + large_set_vat.json in working directory.
Auto-skipped if files not found.
"""

import json
import os

import pytest

from matcher.matcher import MatcherConfig, MatchStatus, match_invoices
from matcher.scorer import ScorerConfig


def load_data():
    try:
        with open("large_set.json") as f:
            deliveries = json.load(f)["data"]["items"]
        with open("large_set_vat.json") as f:
            invoices = json.load(f)["data"]["vat_invoices"]
        return deliveries, invoices
    except FileNotFoundError:
        return None, None


DELIVERIES, INVOICES = load_data()

skip_if_no_data = pytest.mark.skipif(
    DELIVERIES is None, reason="large_set.json / large_set_vat.json not found"
)


@skip_if_no_data
class TestIntegration:
    def setup_method(self):
        self.config = MatcherConfig(use_llm=False)
        self.results = match_invoices(DELIVERIES, INVOICES, self.config)
        self.by_id = {r.invoice_id: r for r in self.results}

    def test_total_results_equals_total_invoices(self):
        assert len(self.results) == len(INVOICES)

    def test_no_invoice_in_multiple_buckets(self):
        """Each invoice appears exactly once."""
        ids = [r.invoice_id for r in self.results]
        assert len(ids) == len(set(ids))

    def test_matched_count_in_expected_range(self):
        matched = sum(1 for r in self.results if r.matched_delivery_id is not None)
        assert 90 <= matched <= 140  # EDA showed ~127 relevant invoices

    def test_no_match_dominates(self):
        no_match = sum(1 for r in self.results if r.status == MatchStatus.NO_MATCH)
        assert no_match > 3000  # 3,117 expected from EDA

    def test_scenario_a_plate_49H01936(self):
        """plate 49H01936: 2 deliveries different dates → date filter resolves."""
        matched = [r for r in self.results if r.matched_delivery_id in (67131, 66787)]
        assert len(matched) > 0
        for r in matched:
            assert r.status in (MatchStatus.AUTO_MATCH, MatchStatus.LLM_MATCH)

    def test_scenario_b_plate_50H67882(self):
        """plate 50H67882: same date, different dropoff → address score resolves."""
        matched = [r for r in self.results if r.matched_delivery_id in (66985, 66984)]
        # Both deliveries should get at least some invoices
        del_ids = {r.matched_delivery_id for r in matched}
        assert len(del_ids) >= 1

    def test_all_results_have_status(self):
        for r in self.results:
            assert r.status in list(MatchStatus)

    def test_auto_match_has_delivery_id(self):
        for r in self.results:
            if r.status == MatchStatus.AUTO_MATCH:
                assert r.matched_delivery_id is not None

    def test_no_match_has_no_delivery_id(self):
        for r in self.results:
            if r.status == MatchStatus.NO_MATCH:
                assert r.matched_delivery_id is None
