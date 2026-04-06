import pytest
from datetime import datetime

from matcher.indexer import build_delivery_index
from tests.fixtures import (
    DELIVERY_72215,
    DELIVERY_72212,
    DELIVERY_72207,
    DELIVERY_72208,
    ALL_DELIVERIES,
)


class TestBuildDeliveryIndex:
    def test_indexes_by_normalized_plate(self):
        index = build_delivery_index([DELIVERY_72215])
        assert '62F00394' in index

    def test_entry_has_required_fields(self):
        index = build_delivery_index([DELIVERY_72215])
        entry = index['62F00394'][0]
        assert entry['id'] == 72215
        assert isinstance(entry['pickup_date'], datetime)
        assert isinstance(entry['dropoff_date'], datetime)
        assert entry['weight_tons'] == 5.54

    def test_unique_plates_each_have_one_entry(self):
        index = build_delivery_index([DELIVERY_72215, DELIVERY_72212])
        assert len(index['62F00394']) == 1
        assert len(index['63H01874']) == 1

    def test_duplicate_plates_grouped_together(self):
        index = build_delivery_index([DELIVERY_72207, DELIVERY_72208])
        entries = index['43C15823']
        assert len(entries) == 2
        ids = {e['id'] for e in entries}
        assert ids == {72207, 72208}

    def test_delivery_without_truck_is_skipped(self):
        delivery_no_truck = {
            'id': 99999,
            'pickup_date': '2025-09-03',
            'dropoff_date': '2025-09-04',
            'weight': 10.0,
            'computed_data': {},
        }
        index = build_delivery_index([delivery_no_truck])
        assert index == {}

    def test_all_deliveries_indexed(self):
        index = build_delivery_index(ALL_DELIVERIES)
        # 4 deliveries but 2 share a plate → 3 distinct keys
        assert len(index) == 3
