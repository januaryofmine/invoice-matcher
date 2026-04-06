from matcher.indexer import build_delivery_index
from tests.fixtures import DEL_66787, DEL_66984, DEL_66985, DEL_67131


class TestBuildDeliveryIndex:
    def test_indexes_by_normalized_plate(self):
        index = build_delivery_index([DEL_67131])
        assert "49H01936" in index

    def test_entry_has_required_fields(self):
        index = build_delivery_index([DEL_67131])
        entry = index["49H01936"][0]
        assert entry["id"] == 67131
        assert entry["pickup_date"] is not None
        assert entry["dropoff_date"] is not None
        assert "weight_tons" in entry
        assert "dropoff_name" in entry
        assert "dropoff_description" in entry

    def test_duplicate_plates_grouped_together(self):
        index = build_delivery_index([DEL_66985, DEL_66984])
        assert "50H67882" in index
        assert len(index["50H67882"]) == 2

    def test_unique_plates_each_have_one_entry(self):
        index = build_delivery_index([DEL_67131, DEL_66985])
        assert len(index["49H01936"]) == 1
        assert len(index["50H67882"]) == 1

    def test_delivery_without_truck_is_skipped(self):
        bad_delivery = {
            "id": 9999,
            "pickup_date": "2025-07-01",
            "dropoff_date": "2025-07-02",
            "weight": 5.0,
            "computed_data": {},
            "dropoff_location": {},
        }
        index = build_delivery_index([bad_delivery])
        assert len(index) == 0

    def test_all_deliveries_indexed(self):
        deliveries = [DEL_67131, DEL_66787, DEL_66985, DEL_66984]
        index = build_delivery_index(deliveries)
        all_ids = [e["id"] for entries in index.values() for e in entries]
        assert set(all_ids) == {67131, 66787, 66985, 66984}
