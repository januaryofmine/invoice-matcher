from collections import defaultdict
from datetime import timedelta

from matcher.normalizer import normalize_plate, parse_date, parse_weight_kg
from matcher.indexer import build_delivery_index, DeliveryEntry


DATE_WINDOW_DAYS = 1  # invoice date must be within pickup-1 .. dropoff+1


def _filter_by_date(candidates: list[DeliveryEntry], inv_date) -> list[DeliveryEntry]:
    """Keep deliveries whose date window covers the invoice date."""
    if not inv_date:
        return candidates  # no invoice date → keep all candidates

    result = []
    for d in candidates:
        lo = d['pickup_date'] - timedelta(days=DATE_WINDOW_DAYS) if d['pickup_date'] else None
        hi = d['dropoff_date'] + timedelta(days=DATE_WINDOW_DAYS) if d['dropoff_date'] else None

        if lo and hi and lo <= inv_date <= hi:
            result.append(d)
        elif not lo and not hi:
            result.append(d)  # delivery has no dates → keep

    return result


def _tiebreak_by_weight(candidates: list[DeliveryEntry], inv_weight_tons: float) -> DeliveryEntry:
    """When multiple deliveries share a plate, pick the one with closest weight."""
    def diff(d):
        w = d.get('weight_tons')
        return abs(w - inv_weight_tons) if w is not None else float('inf')

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
        norm_plate = normalize_plate(inv.get('truck_plate'))

        # Step 1: plate lookup
        if not norm_plate or norm_plate not in index:
            unmatched.append(inv['id'])
            continue

        candidates = index[norm_plate]

        # Step 2: date filter
        inv_date = parse_date((inv.get('metadata') or {}).get('(Date)'))
        candidates = _filter_by_date(candidates, inv_date)

        if not candidates:
            unmatched.append(inv['id'])
            continue

        # Step 3: assign (tiebreak if needed)
        inv_weight_tons = parse_weight_kg(inv.get('sku_data')) / 1000
        if len(candidates) == 1:
            best = candidates[0]
        else:
            best = _tiebreak_by_weight(candidates, inv_weight_tons)

        matched[best['id']].append(inv['id'])

    return {
        'matches': dict(matched),
        'unmatched_invoice_ids': unmatched,
        'stats': {
            'total_invoices': len(invoices),
            'matched_invoices': sum(len(v) for v in matched.values()),
            'unmatched_invoices': len(unmatched),
            'deliveries_with_match': len(matched),
            'deliveries_without_match': len(deliveries) - len(matched),
        },
    }
