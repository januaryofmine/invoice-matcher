import pytest

from matcher.matcher import match_invoices
from tests.fixtures import (
    DELIVERY_72215, DELIVERY_72212, DELIVERY_72207, DELIVERY_72208,
    INVOICE_35052755,
    INVOICE_35052984, INVOICE_35052986, INVOICE_35052988,
    INVOICE_35052990, INVOICE_35052992,
    INVOICE_35053243, INVOICE_35053245,
    UNRELATED_INVOICE, NO_PLATE_INVOICE, OUT_OF_DATE_INVOICE,
    ALL_DELIVERIES, ALL_INVOICES,
)


class TestPlateMatching:
    def test_invoice_with_no_matching_plate_is_unmatched(self):
        result = match_invoices([DELIVERY_72215], [UNRELATED_INVOICE])
        assert UNRELATED_INVOICE['id'] in result['unmatched_invoice_ids']

    def test_invoice_with_no_plate_is_unmatched(self):
        result = match_invoices([DELIVERY_72215], [NO_PLATE_INVOICE])
        assert NO_PLATE_INVOICE['id'] in result['unmatched_invoice_ids']

    def test_invoice_matching_plate_is_matched(self):
        result = match_invoices([DELIVERY_72215], [INVOICE_35052755])
        assert 72215 in result['matches']
        assert INVOICE_35052755['id'] in result['matches'][72215]


class TestDateFiltering:
    def test_invoice_inside_date_window_is_matched(self):
        result = match_invoices([DELIVERY_72215], [INVOICE_35052755])
        # invoice date 03/09 is within pickup 03/09 - dropoff 04/09 window
        assert INVOICE_35052755['id'] in result['matches'].get(72215, [])

    def test_invoice_outside_date_window_is_unmatched(self):
        result = match_invoices([DELIVERY_72215], [OUT_OF_DATE_INVOICE])
        assert OUT_OF_DATE_INVOICE['id'] in result['unmatched_invoice_ids']

    def test_invoice_with_no_date_is_kept_as_candidate(self):
        no_date_invoice = {
            'id': 55555555,
            'truck_plate': '62F-003.94',
            'metadata': {},  # no (Date) key
            'sku_data': {'net_weight': 4000.0},
        }
        result = match_invoices([DELIVERY_72215], [no_date_invoice])
        assert 55555555 in result['matches'].get(72215, [])


class TestMultipleInvoicesPerDelivery:
    def test_all_five_invoices_assigned_to_72212(self):
        result = match_invoices([DELIVERY_72212], [
            INVOICE_35052984, INVOICE_35052986, INVOICE_35052988,
            INVOICE_35052990, INVOICE_35052992,
        ])
        matched = set(result['matches'].get(72212, []))
        expected = {35052984, 35052986, 35052988, 35052990, 35052992}
        assert matched == expected


class TestWeightTiebreak:
    def test_duplicate_plate_invoices_assigned_consistently(self):
        """
        72207 and 72208 share plate 43C-158.23.
        Both invoices have NaN weight → tiebreak by weight is impossible,
        but result must be deterministic (no crash, all invoices assigned).
        """
        result = match_invoices([DELIVERY_72207, DELIVERY_72208], [
            INVOICE_35053243, INVOICE_35053245,
        ])
        all_matched = set()
        for ids in result['matches'].values():
            all_matched.update(ids)

        assert 35053243 in all_matched
        assert 35053245 in all_matched
        assert result['stats']['unmatched_invoices'] == 0

    def test_weight_tiebreak_prefers_closer_delivery(self):
        """
        Two deliveries share a plate. One invoice has weight clearly closer
        to one of them → should be assigned to that delivery.
        """
        del_light = {
            'id': 1001,
            'pickup_date': '2025-09-03', 'dropoff_date': '2025-09-04',
            'weight': 5.0,
            'computed_data': {'truck': {'plate': 'XX-000.00'}},
        }
        del_heavy = {
            'id': 1002,
            'pickup_date': '2025-09-03', 'dropoff_date': '2025-09-04',
            'weight': 20.0,
            'computed_data': {'truck': {'plate': 'XX-000.00'}},
        }
        inv_close_to_light = {
            'id': 2001,
            'truck_plate': 'XX-000.00',
            'metadata': {'(Date)': '03/09/2025'},
            'sku_data': {'net_weight': 4800.0},  # 4.8 tons → closer to 5.0
        }
        result = match_invoices([del_light, del_heavy], [inv_close_to_light])
        assert 2001 in result['matches'].get(1001, [])
        assert 2001 not in result['matches'].get(1002, [])


class TestStats:
    def test_stats_are_accurate(self):
        result = match_invoices(ALL_DELIVERIES, ALL_INVOICES)
        stats = result['stats']
        assert stats['total_invoices'] == len(ALL_INVOICES)
        assert stats['matched_invoices'] + stats['unmatched_invoices'] == stats['total_invoices']
        assert stats['deliveries_with_match'] + stats['deliveries_without_match'] == len(ALL_DELIVERIES)

    def test_unmatched_invoices_not_in_matches(self):
        result = match_invoices([DELIVERY_72215], [INVOICE_35052755, UNRELATED_INVOICE])
        all_matched = {i for ids in result['matches'].values() for i in ids}
        for inv_id in result['unmatched_invoice_ids']:
            assert inv_id not in all_matched
