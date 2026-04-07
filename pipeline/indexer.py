"""
Delivery index builder.

Responsibility (SRP): build and return the plate → [DeliveryEntry] lookup
structure.  Nothing else — no scoring, no matching, no I/O.

The index is built once before the main loop in matcher.py and then used
as a read-only data structure.  This makes candidate lookup O(1) per invoice
instead of O(n_deliveries).
"""

from collections import defaultdict

from pipeline.normalizer import normalize_plate, parse_date, parse_weight_tons
from core.types import DeliveryEntry


# ── Internal helpers ──────────────────────────────────────────────────────────


def _build_entry(delivery: dict) -> DeliveryEntry:
    """
    Transform one raw delivery record into a normalized DeliveryEntry.

    The raw record comes directly from the API / JSON file and has a deeply
    nested, inconsistent shape.  This function is the single place that knows
    about that raw shape — the rest of the pipeline only ever sees DeliveryEntry.

    Steps:
      1. Safely navigate the nested truck sub-object (may be absent).
      2. Safely navigate the dropoff_location sub-object (may be absent).
      3. Build and return a DeliveryEntry with all fields normalized.
    """
    # Step 1 — truck data lives two levels deep; guard each level with `or {}`
    truck = (delivery.get("computed_data") or {}).get("truck") or {}

    # Step 2 — dropoff location also nested; default to empty dict on absence
    dropoff_loc = delivery.get("dropoff_location") or {}

    # Step 3 — build the flat, normalized entry that the rest of the pipeline uses
    return DeliveryEntry(
        id=delivery["id"],
        pickup_date=parse_date(delivery.get("pickup_date")),
        dropoff_date=parse_date(delivery.get("dropoff_date")),
        weight_tons=parse_weight_tons(delivery),
        dropoff_name=dropoff_loc.get("name") or "",
        dropoff_description=dropoff_loc.get("description") or "",
        dropoff_location_id=delivery.get("dropoff_location_id"),
    )


# ── Public API ────────────────────────────────────────────────────────────────


def build_delivery_index(deliveries: list[dict]) -> dict[str, list[DeliveryEntry]]:
    """
    Build a plate → deliveries lookup index from the raw delivery list.

    Why an index?
      Without it, every invoice would scan all ~N deliveries linearly.
      With it, candidate lookup is O(1) average case (dict hash lookup).

    Why list[DeliveryEntry] per plate?
      The same truck (plate) may appear on multiple deliveries — multi-stop
      routes are common in Vietnamese logistics.  All of them must be considered
      as candidates for an invoice that references that plate.

    Steps:
      1. Initialise a defaultdict so appending to unseen plates works cleanly.
      2. For each delivery, extract and normalize the plate.
      3. Skip deliveries with no usable plate (can't be matched by plate anyway).
      4. Build and store a normalized DeliveryEntry under the plate key.
      5. Return as a plain dict (no defaultdict in the public API — callers
         should use .get() and handle the None case explicitly).

    Args:
        deliveries: Raw delivery records as loaded from the JSON source.

    Returns:
        Dict mapping normalized plate strings to lists of DeliveryEntry objects.
    """
    # Step 1 — defaultdict avoids an explicit key-existence check on every append
    index: dict[str, list[DeliveryEntry]] = defaultdict(list)

    for delivery in deliveries:
        # Step 2 — plate lives inside computed_data.truck; normalize for lookup
        truck = (delivery.get("computed_data") or {}).get("truck") or {}
        plate = normalize_plate(truck.get("plate"))

        # Step 3 — no plate means we can never match this delivery by plate
        if not plate:
            continue

        # Step 4 — store the normalized entry under the canonical plate key
        index[plate].append(_build_entry(delivery))

    # Step 5 — convert to plain dict; callers use index.get(plate, [])
    return dict(index)
