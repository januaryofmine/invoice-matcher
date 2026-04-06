from unittest.mock import patch

import pytest

from matcher.matcher import _tokenize, match_invoices
from tests.fixtures import (
    ALL_DELIVERIES,
    ALL_INVOICES,
    DELIVERY_72207,
    DELIVERY_72208,
    DELIVERY_72212,
    DELIVERY_72215,
    INVOICE_35052755,
    INVOICE_35052984,
    INVOICE_35052986,
    INVOICE_35052988,
    INVOICE_35052990,
    INVOICE_35052992,
    INVOICE_35053243,
    INVOICE_35053245,
    NO_PLATE_INVOICE,
    OUT_OF_DATE_INVOICE,
    UNRELATED_INVOICE,
)

EMPTY_PROVINCE_MAP = {}


class TestStep1PlateCheck:
    def test_no_plate_goes_to_manual_review(self):
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices([DELIVERY_72215], [NO_PLATE_INVOICE])
        manual_ids = [i["id"] for i in result["manual_review"]]
        assert NO_PLATE_INVOICE["id"] in manual_ids

    def test_no_plate_reason(self):
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices([DELIVERY_72215], [NO_PLATE_INVOICE])
        item = next(
            i for i in result["manual_review"] if i["id"] == NO_PLATE_INVOICE["id"]
        )
        assert item["reason"] == "no_plate"

    def test_plate_not_in_system_is_unmatched(self):
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices([DELIVERY_72215], [UNRELATED_INVOICE])
        assert UNRELATED_INVOICE["id"] in result["unmatched_invoice_ids"]


class TestStep2DateWindow:
    def test_date_out_of_window_goes_to_manual_review(self):
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices([DELIVERY_72215], [OUT_OF_DATE_INVOICE])
        item = next(
            i for i in result["manual_review"] if i["id"] == OUT_OF_DATE_INVOICE["id"]
        )
        assert item["reason"] == "date_out_of_window"

    def test_single_candidate_assigns_directly(self):
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices([DELIVERY_72215], [INVOICE_35052755])
        assert INVOICE_35052755["id"] in result["matches"].get(72215, [])


class TestStep3aProvinceCheck:
    def test_province_mismatch_goes_to_manual_review(self):
        province_map = {
            "LÔ 37 BÙI TÁ HÁN, PHƯỜNG NGŨ HÀNH SƠN, THÀNH PHỐ ĐÀ NẴNG, VIỆT NAM": "Đà Nẵng",
            DELIVERY_72207["dropoff_location"]["description"]: "Hồ Chí Minh",
            DELIVERY_72208["dropoff_location"]["description"]: "Hồ Chí Minh",
        }
        with patch("matcher.matcher.extract_provinces", return_value=province_map):
            result = match_invoices(
                [DELIVERY_72207, DELIVERY_72208],
                [INVOICE_35053243],
            )
        item = next(
            i for i in result["manual_review"] if i["id"] == INVOICE_35053243["id"]
        )
        assert item["reason"] == "province_mismatch"

    def test_province_fail_falls_through_to_3b(self):
        """When LLM fails (empty provinces), skip 3a and use token overlap."""
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices(
                [DELIVERY_72207, DELIVERY_72208],
                [INVOICE_35053243, INVOICE_35053245],
            )
        # Token overlap should still resolve correctly
        assert INVOICE_35053243["id"] in result["matches"].get(72207, [])
        assert INVOICE_35053245["id"] in result["matches"].get(72208, [])


class TestStep3bTokenOverlap:
    def test_token_overlap_resolves_duplicate_plate(self):
        """Street-level token overlap distinguishes 72207 vs 72208."""
        province_map = {
            "LÔ 37 BÙI TÁ HÁN, PHƯỜNG NGŨ HÀNH SƠN, THÀNH PHỐ ĐÀ NẴNG, VIỆT NAM": "Đà Nẵng",
            "571 NGUYỄN TẤT THÀNH, PHƯỜNG THANH KHÊ, THÀNH PHỐ ĐÀ NẴNG, VIỆT NAM": "Đà Nẵng",
            DELIVERY_72207["dropoff_location"]["description"]: "Đà Nẵng",
            DELIVERY_72208["dropoff_location"]["description"]: "Đà Nẵng",
        }
        with patch("matcher.matcher.extract_provinces", return_value=province_map):
            result = match_invoices(
                [DELIVERY_72207, DELIVERY_72208],
                [INVOICE_35053243, INVOICE_35053245],
            )
        assert INVOICE_35053243["id"] in result["matches"].get(72207, [])
        assert INVOICE_35053245["id"] in result["matches"].get(72208, [])

    def test_tokenize_strips_stopwords(self):
        tokens = _tokenize("CÔNG TY TNHH BÙI TÁ HÁN, PHƯỜNG NGŨ HÀNH SƠN")
        assert "CONG" not in tokens
        assert "TNHH" not in tokens
        assert "PHUONG" not in tokens


class TestStep4WeightTiebreak:
    def test_weight_picks_closest(self):
        del_light = {
            "id": 1001,
            "pickup_date": "2025-09-03",
            "dropoff_date": "2025-09-04",
            "weight": 5.0,
            "computed_data": {"truck": {"plate": "AA-111.11"}},
            "dropoff_location": {"name": "", "description": "Quận 1 HCM"},
            "broker_company": {"name": ""},
        }
        del_heavy = {
            "id": 1002,
            "pickup_date": "2025-09-03",
            "dropoff_date": "2025-09-04",
            "weight": 20.0,
            "computed_data": {"truck": {"plate": "AA-111.11"}},
            "dropoff_location": {"name": "", "description": "Quận 2 HCM"},
            "broker_company": {"name": ""},
        }
        inv = {
            "id": 2001,
            "truck_plate": "AA-111.11",
            "metadata": {"(Date)": "03/09/2025", "(Delivery address)": "Quận 9 HCM"},
            "sku_data": {"net_weight": 4800.0},
        }
        province_map = {
            "Quận 9 HCM": "Hồ Chí Minh",
            "Quận 1 HCM": "Hồ Chí Minh",
            "Quận 2 HCM": "Hồ Chí Minh",
        }
        with patch("matcher.matcher.extract_provinces", return_value=province_map):
            result = match_invoices([del_light, del_heavy], [inv])
        assert 2001 in result["matches"].get(1001, [])

    def test_unclear_when_all_weights_none(self):
        del_a = {
            "id": 3001,
            "pickup_date": "2025-09-03",
            "dropoff_date": "2025-09-04",
            "weight": None,
            "computed_data": {"truck": {"plate": "BB-222.22"}},
            "dropoff_location": {"name": "", "description": "Địa chỉ A"},
            "broker_company": {"name": ""},
        }
        del_b = {
            "id": 3002,
            "pickup_date": "2025-09-03",
            "dropoff_date": "2025-09-04",
            "weight": None,
            "computed_data": {"truck": {"plate": "BB-222.22"}},
            "dropoff_location": {"name": "", "description": "Địa chỉ B"},
            "broker_company": {"name": ""},
        }
        inv = {
            "id": 4001,
            "truck_plate": "BB-222.22",
            "metadata": {"(Date)": "03/09/2025", "(Delivery address)": "Địa chỉ C"},
            "sku_data": {"net_weight": None},
        }
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices([del_a, del_b], [inv])
        item = next(i for i in result["manual_review"] if i["id"] == 4001)
        assert item["reason"] == "unclear_details"


class TestMultipleInvoicesPerDelivery:
    def test_all_five_invoices_assigned_to_72212(self):
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices(
                [DELIVERY_72212],
                [
                    INVOICE_35052984,
                    INVOICE_35052986,
                    INVOICE_35052988,
                    INVOICE_35052990,
                    INVOICE_35052992,
                ],
            )
        matched = set(result["matches"].get(72212, []))
        assert matched == {35052984, 35052986, 35052988, 35052990, 35052992}


class TestStats:
    def test_total_accounted_for(self):
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices(ALL_DELIVERIES, ALL_INVOICES)
        stats = result["stats"]
        total = (
            stats["matched_invoices"]
            + stats["unmatched_invoices"]
            + stats["manual_review_invoices"]
        )
        assert total == stats["total_invoices"]

    def test_no_invoice_in_both_matched_and_manual(self):
        with patch(
            "matcher.matcher.extract_provinces", return_value=EMPTY_PROVINCE_MAP
        ):
            result = match_invoices(
                [DELIVERY_72215], [INVOICE_35052755, UNRELATED_INVOICE]
            )
        all_matched = {i for ids in result["matches"].values() for i in ids}
        for item in result["manual_review"]:
            assert item["id"] not in all_matched
