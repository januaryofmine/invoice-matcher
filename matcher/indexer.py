from collections import defaultdict
from datetime import datetime

from matcher.normalizer import normalize_plate, parse_date

DeliveryEntry = dict  # typed alias for readability


def build_delivery_index(deliveries: list[dict]) -> dict[str, list[DeliveryEntry]]:
    """
    Build a lookup index: normalized_plate -> list of delivery entries.
    Multiple deliveries can share the same plate (handled downstream).

    Each entry contains:
        id, pickup_date, dropoff_date, weight_tons,
        dropoff_name, dropoff_address, broker_name
    """
    index: dict[str, list[DeliveryEntry]] = defaultdict(list)

    for d in deliveries:
        truck = (d.get("computed_data") or {}).get("truck") or {}
        plate = normalize_plate(truck.get("plate"))
        if not plate:
            continue

        dropoff_loc = d.get("dropoff_location") or {}
        broker = d.get("broker_company") or {}
        dropoff_desc = dropoff_loc.get("description") or ""
        index[plate].append(
            {
                "id": d["id"],
                "pickup_date": parse_date(d.get("pickup_date")),
                "dropoff_date": parse_date(d.get("dropoff_date")),
                "weight_tons": d.get("weight"),
                "dropoff_name": (dropoff_loc.get("name") or "").upper(),
                "dropoff_address": dropoff_desc.upper(),
                "dropoff_address_raw": dropoff_desc,
                "broker_name": (broker.get("name") or "").upper(),
            }
        )

    return dict(index)


def build_all_delivery_entries(deliveries: list[dict]) -> list[DeliveryEntry]:
    """
    Return all deliveries as a flat list of entries — used by pipeline B
    (no-plate invoices) which must search across all deliveries.
    """
    entries = []
    for d in deliveries:
        dropoff_loc = d.get("dropoff_location") or {}
        broker = d.get("broker_company") or {}
        dropoff_desc = dropoff_loc.get("description") or ""
        entries.append(
            {
                "id": d["id"],
                "pickup_date": parse_date(d.get("pickup_date")),
                "dropoff_date": parse_date(d.get("dropoff_date")),
                "weight_tons": d.get("weight"),
                "dropoff_name": (dropoff_loc.get("name") or "").upper(),
                "dropoff_address": dropoff_desc.upper(),
                "dropoff_address_raw": dropoff_desc,
                "broker_name": (broker.get("name") or "").upper(),
            }
        )
    return entries
