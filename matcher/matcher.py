from collections import defaultdict
from datetime import timedelta

from matcher.indexer import DeliveryEntry, build_delivery_index
from matcher.normalizer import normalize_plate, parse_date, parse_weight_kg

DATE_WINDOW_DAYS = 1  # invoice date must be within pickup-1 .. dropoff+1


def _filter_by_date(candidates: list[DeliveryEntry], inv_date) -> list[DeliveryEntry]:
    """Keep deliveries whose date window covers the invoice date."""
    if not inv_date:
        return candidates  # no invoice date → keep all candidates

    result = []
    for d in candidates:
        lo = (
            d["pickup_date"] - timedelta(days=DATE_WINDOW_DAYS)
            if d["pickup_date"]
            else None
        )
        hi = (
            d["dropoff_date"] + timedelta(days=DATE_WINDOW_DAYS)
            if d["dropoff_date"]
            else None
        )

        if lo and hi and lo <= inv_date <= hi:
            result.append(d)
        elif not lo and not hi:
            result.append(d)  # delivery has no dates → keep

    return result


def _tiebreak_by_location(
    candidates: list[DeliveryEntry], inv_delivery_address: str
) -> list[DeliveryEntry]:
    """
    Filter candidates by matching invoice delivery address against
    dropoff name or dropoff address. Uses keyword overlap — no fuzzy needed
    since both sides are structured Vietnamese address strings.

    Returns filtered list if any match found, else original list (fallback).
    """
    if not inv_delivery_address:
        return candidates

    # Tokenize address into meaningful words (skip short tokens)
    inv_tokens = {w for w in inv_delivery_address.upper().split() if len(w) > 3}
    if not inv_tokens:
        return candidates

    def overlap_score(d: DeliveryEntry) -> int:
        haystack = f"{d.get('dropoff_name', '')} {d.get('dropoff_address', '')}".upper()
        return sum(1 for token in inv_tokens if token in haystack)

    scored = [(overlap_score(d), d) for d in candidates]
    best_score = max(s for s, _ in scored)

    if best_score == 0:
        return candidates  # no location signal → fallback to weight

    return [d for s, d in scored if s == best_score]


def _tiebreak_by_weight(
    candidates: list[DeliveryEntry], inv_weight_tons: float
) -> DeliveryEntry:
    """When multiple deliveries share a plate, pick the one with closest weight."""

    def diff(d):
        w = d.get("weight_tons")
        return abs(w - inv_weight_tons) if w is not None else float("inf")

    return min(candidates, key=diff)


def match_invoices(deliveries: list[dict], invoices: list[dict]) -> dict:
    """
    Match VAT invoices to deliveries.

    Returns:
        {
            'matches': { delivery_id: [invoice_id, ...] },
            'unmatched_invoice_ids': [...],
            'stats': { ... }
        }
    """
    index = build_delivery_index(deliveries)
    matched: dict[int, list[int]] = defaultdict(list)
    unmatched: list[int] = []

    for inv in invoices:
        norm_plate = normalize_plate(inv.get("truck_plate"))

        # Step 1: plate lookup
        if not norm_plate or norm_plate not in index:
            unmatched.append(inv["id"])
            continue

        candidates = index[norm_plate]

        # Step 2: date filter
        inv_date = parse_date((inv.get("metadata") or {}).get("(Date)"))
        candidates = _filter_by_date(candidates, inv_date)

        if not candidates:
            unmatched.append(inv["id"])
            continue

        # Step 3: assign (tiebreak if needed)
        inv_weight_tons = parse_weight_kg(inv.get("sku_data")) / 1000
        inv_delivery_address = (inv.get("metadata") or {}).get("(Delivery address)", "")

        if len(candidates) == 1:
            best = candidates[0]
        else:
            # 3a: location tiebreak (primary — works even when weight is NaN)
            candidates = _tiebreak_by_location(candidates, inv_delivery_address)
            # 3b: weight tiebreak (fallback — when location gives no signal)
            best = _tiebreak_by_weight(candidates, inv_weight_tons)

        matched[best["id"]].append(inv["id"])

    return {
        "matches": dict(matched),
        "unmatched_invoice_ids": unmatched,
        "stats": {
            "total_invoices": len(invoices),
            "matched_invoices": sum(len(v) for v in matched.values()),
            "unmatched_invoices": len(unmatched),
            "deliveries_with_match": len(matched),
            "deliveries_without_match": len(deliveries) - len(matched),
        },
    }
