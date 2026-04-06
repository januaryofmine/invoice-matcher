"""
Build lookup indexes for fast candidate generation.
"""

from collections import defaultdict
from datetime import datetime

from matcher.normalizer import normalize_plate, parse_date, parse_weight_tons

DeliveryEntry = dict


def _build_entry(delivery: dict) -> DeliveryEntry:
    """Extract and normalize all fields needed for matching from a delivery."""
    truck = (delivery.get("computed_data") or {}).get("truck") or {}
    dropoff_loc = delivery.get("dropoff_location") or {}

    return {
        "id": delivery["id"],
        "pickup_date": parse_date(delivery.get("pickup_date")),
        "dropoff_date": parse_date(delivery.get("dropoff_date")),
        "weight_tons": parse_weight_tons(delivery),
        "dropoff_name": dropoff_loc.get("name") or "",
        "dropoff_description": dropoff_loc.get("description") or "",
        "dropoff_location_id": delivery.get("dropoff_location_id"),
    }


def build_delivery_index(deliveries: list[dict]) -> dict[str, list[DeliveryEntry]]:
    """
    Build plate → list of delivery entries index.
    Multiple deliveries can share the same plate (multi-stop routes).
    """
    index: dict[str, list[DeliveryEntry]] = defaultdict(list)

    for d in deliveries:
        truck = (d.get("computed_data") or {}).get("truck") or {}
        plate = normalize_plate(truck.get("plate"))
        if not plate:
            continue
        index[plate].append(_build_entry(d))

    return dict(index)
