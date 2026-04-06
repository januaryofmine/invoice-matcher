"""
Integration test — uses the real 20250901.json file.
Place the file at the project root before running.
"""

import json
from pathlib import Path

import pytest

from matcher.matcher import match_invoices

DATA_FILE = Path(__file__).parent.parent / "20250901.json"


@pytest.fixture(scope="module")
def real_data():
    if not DATA_FILE.exists():
        pytest.skip(f"Data file not found: {DATA_FILE}")
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)["data"]
    return data


@pytest.fixture(scope="module")
def real_result(real_data):
    return match_invoices(real_data["deliveries"], real_data["vat_invoices"])


class TestIntegration:
    def test_total_invoice_count(self, real_data):
        assert len(real_data["vat_invoices"]) == 680

    def test_total_delivery_count(self, real_data):
        assert len(real_data["deliveries"]) == 10

    def test_matched_invoice_count(self, real_result):
        assert real_result["stats"]["matched_invoices"] == 20

    def test_unmatched_invoice_count(self, real_result):
        assert real_result["stats"]["unmatched_invoices"] == 660

    def test_deliveries_with_match(self, real_result):
        assert real_result["stats"]["deliveries_with_match"] == 10

    def test_deliveries_without_match(self, real_result):
        assert real_result["stats"]["deliveries_without_match"] == 0

    def test_known_match_72215(self, real_result):
        assert real_result["matches"].get(72215) == [35052755]

    def test_known_match_72212_has_five_invoices(self, real_result):
        assert len(real_result["matches"].get(72212, [])) == 5

    def test_known_match_72206(self, real_result):
        assert real_result["matches"].get(72206) == [35053219]

    def test_location_tiebreak_72207(self, real_result):
        """35053243 (Ngũ Hành Sơn) should resolve to 72207 (GIA TRƯỜNG PHÚC)."""
        assert 35053243 in real_result["matches"].get(72207, [])

    def test_location_tiebreak_72208(self, real_result):
        """35053245 (Thanh Khê) should resolve to 72208 (T.A.S.T.Y)."""
        assert 35053245 in real_result["matches"].get(72208, [])

    def test_no_invoice_assigned_to_multiple_deliveries(self, real_result):
        """Each invoice must appear in at most one delivery's list."""
        seen = {}
        for did, inv_ids in real_result["matches"].items():
            for inv_id in inv_ids:
                assert inv_id not in seen, (
                    f"Invoice {inv_id} assigned to both {seen[inv_id]} and {did}"
                )
                seen[inv_id] = did

    def test_matched_plus_unmatched_equals_total(self, real_result):
        stats = real_result["stats"]
        assert (
            stats["matched_invoices"] + stats["unmatched_invoices"]
            == stats["total_invoices"]
        )
