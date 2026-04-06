"""
Integration test — uses the real 20250901.json file.
Province extraction uses the real LLM (requires ANTHROPIC_API_KEY).
Tests skip if data file or API key is missing.
"""

import json
import os
from pathlib import Path

import pytest

from matcher.matcher import match_invoices

DATA_FILE = Path(__file__).parent.parent / "20250901.json"
HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.fixture(scope="module")
def real_data():
    if not DATA_FILE.exists():
        pytest.skip(f"Data file not found: {DATA_FILE}")
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)["data"]
    return data


@pytest.fixture(scope="module")
def real_result(real_data):
    if not HAS_API_KEY:
        pytest.skip("ANTHROPIC_API_KEY not set — skipping LLM integration tests")
    return match_invoices(real_data["deliveries"], real_data["vat_invoices"])


class TestIntegration:
    def test_total_invoice_count(self, real_data):
        assert len(real_data["vat_invoices"]) == 680

    def test_total_delivery_count(self, real_data):
        assert len(real_data["deliveries"]) == 10

    def test_invoices_with_and_without_plate(self, real_result):
        stats = real_result["stats"]
        assert stats["invoices_with_plate"] == 667
        assert stats["invoices_without_plate"] == 13

    def test_matched_plus_unmatched_equals_total(self, real_result):
        stats = real_result["stats"]
        total = (
            stats["matched_invoices"]
            + stats["unmatched_invoices"]
            + stats["manual_review_invoices"]
        )
        assert total == stats["total_invoices"]

    def test_known_match_72215(self, real_result):
        assert real_result["matches"].get(72215) == [35052755]

    def test_known_match_72212_has_five_invoices(self, real_result):
        assert len(real_result["matches"].get(72212, [])) == 5

    def test_known_match_72206(self, real_result):
        assert real_result["matches"].get(72206) == [35053219]

    def test_no_invoice_assigned_to_multiple_deliveries(self, real_result):
        """Each invoice must appear in at most one delivery's list."""
        seen = {}
        for did, inv_ids in real_result["matches"].items():
            for inv_id in inv_ids:
                assert inv_id not in seen, (
                    f"Invoice {inv_id} assigned to both {seen[inv_id]} and {did}"
                )
                seen[inv_id] = did

    def test_deliveries_with_match(self, real_result):
        assert real_result["stats"]["deliveries_with_match"] == 10

    def test_deliveries_without_match(self, real_result):
        assert real_result["stats"]["deliveries_without_match"] == 0
