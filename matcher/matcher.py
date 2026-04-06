from collections import defaultdict
from datetime import timedelta

from matcher.indexer import DeliveryEntry, build_delivery_index
from matcher.normalizer import normalize_plate, parse_date, parse_weight_kg
from matcher.province_extractor import extract_provinces, provinces_match

DATE_WINDOW_DAYS = 1

_STOPWORDS = {
    "CONG",
    "TNHH",
    "THANH",
    "PHUONG",
    "PHO",
    "QUAN",
    "HUYEN",
    "TINH",
    "DUONG",
    "VIET",
    "NAM",
    "KHU",
    "SO",
    "LOT",
    "BLOCK",
    "PHAN",
    "TRACH",
    "NHIEM",
    "HUU",
    "HAN",
    "CO",
    "CHI",
    "NHANH",
    "LIEN",
    "HIEP",
    "HOP",
    "TAC",
    "XA",
    "NUOC",
    "KHAC",
    "TONG",
}

# Manual review reason codes
REASON_NO_PLATE = "no_plate"
REASON_DATE_OUT_OF_WINDOW = "date_out_of_window"
REASON_PROVINCE_MISMATCH = "province_mismatch"
REASON_UNCLEAR_DETAILS = "unclear_details"


# ── Step 2: date window ───────────────────────────────────────────────────────


def _filter_by_date(candidates: list[DeliveryEntry], inv_date) -> list[DeliveryEntry]:
    if not inv_date:
        return candidates
    result = []
    for c in candidates:
        lo = (
            c["pickup_date"] - timedelta(days=DATE_WINDOW_DAYS)
            if c["pickup_date"]
            else None
        )
        hi = (
            c["dropoff_date"] + timedelta(days=DATE_WINDOW_DAYS)
            if c["dropoff_date"]
            else None
        )
        if lo and hi and lo <= inv_date <= hi:
            result.append(c)
        elif not lo and not hi:
            result.append(c)
    return result


# ── Step 3a: LLM province filter ─────────────────────────────────────────────


def _filter_by_province(
    candidates: list[DeliveryEntry],
    inv_province: str,
    province_map: dict[str, str],
) -> tuple[list[DeliveryEntry], bool]:
    """
    Filter candidates by province match.
    Returns (filtered, signal_available).
    signal_available=False means LLM failed → skip this step.
    """
    if not inv_province:
        return candidates, False

    any_dropoff_has_province = any(
        province_map.get(c.get("dropoff_address_raw", ""), "") for c in candidates
    )
    if not any_dropoff_has_province:
        return candidates, False  # LLM failed → skip

    filtered = [
        c
        for c in candidates
        if not province_map.get(
            c.get("dropoff_address_raw", ""), ""
        )  # no province data → keep
        or provinces_match(
            inv_province, province_map.get(c.get("dropoff_address_raw", ""), "")
        )
    ]
    return filtered, True


# ── Step 3b: token overlap address match ─────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Tokenize Vietnamese address, filtering stopwords and short tokens."""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text.upper())
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    tokens = ascii_str.replace(",", " ").replace(".", " ").split()
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


def _filter_by_token_overlap(
    candidates: list[DeliveryEntry],
    inv_address: str,
) -> list[DeliveryEntry]:
    """
    Filter candidates by token overlap between invoice delivery address
    and delivery dropoff address.
    Returns filtered list if any candidate has overlap > 0, else original list.
    """
    if not inv_address:
        return candidates

    inv_tokens = _tokenize(inv_address)
    if not inv_tokens:
        return candidates

    def score(c: DeliveryEntry) -> int:
        dropoff = c.get("dropoff_address", "") or c.get("dropoff_address_raw", "")
        return len(inv_tokens & _tokenize(dropoff))

    scored = [(score(c), c) for c in candidates]
    best = max(s for s, _ in scored)

    if best == 0:
        return candidates  # no signal → fallback to weight

    return [c for s, c in scored if s == best]


# ── Step 4: weight tiebreak ───────────────────────────────────────────────────


def _tiebreak_by_weight(
    candidates: list[DeliveryEntry], inv_weight_tons: float
) -> list[DeliveryEntry]:
    def diff(d):
        w = d.get("weight_tons")
        return abs(w - inv_weight_tons) if w is not None else float("inf")

    scores = [(diff(d), d) for d in candidates]
    best_score = min(s for s, _ in scores)

    if best_score == float("inf"):
        return candidates  # no weight signal → cannot decide

    return [d for s, d in scores if s == best_score]


# ── Orchestrator ──────────────────────────────────────────────────────────────


def match_invoices(deliveries: list[dict], invoices: list[dict]) -> dict:
    """
    Step 1: Plate check
      - Has plate + found   → candidates → step 2
      - Has plate + missing → unmatched
      - No plate            → manual_review (no_plate)

    Step 2: Date window [pickup-1, dropoff+1]
      - 1 candidate         → assign
      - >1 candidates       → step 3a
      - 0 candidates        → manual_review (date_out_of_window)

    Step 3a: LLM province check (skipped gracefully if API unavailable)
      - 1 candidate         → assign
      - >1 candidates       → step 3b
      - 0 candidates        → manual_review (province_mismatch)

    Step 3b: Token overlap address match
      - 1 candidate         → assign
      - >1 candidates       → step 4
      - 0 candidates        → step 4 (fallback: keep all)

    Step 4: Weight tiebreak
      - 1 candidate         → assign
      - >1 candidates       → manual_review (unclear_details)
    """
    index = build_delivery_index(deliveries)

    matched: dict[int, list[int]] = defaultdict(list)
    unmatched: list[int] = []
    manual_review: list[dict] = []

    # Step 1: split by plate
    with_plate = []
    for inv in invoices:
        norm_plate = normalize_plate(inv.get("truck_plate"))
        if not norm_plate:
            manual_review.append({"id": inv["id"], "reason": REASON_NO_PLATE})
            continue
        if norm_plate not in index:
            unmatched.append(inv["id"])
            continue
        with_plate.append({"invoice": inv, "candidates": list(index[norm_plate])})

    # Batch province extraction — 1 LLM call
    inv_addresses = [
        (p["invoice"].get("metadata") or {}).get("(Delivery address)", "")
        for p in with_plate
    ]
    dropoff_addresses = list(
        {c.get("dropoff_address_raw", "") for p in with_plate for c in p["candidates"]}
    )
    province_map = extract_provinces(list(set(inv_addresses + dropoff_addresses)))

    # Step 2 → 3a → 3b → 4
    for p in with_plate:
        inv = p["invoice"]
        candidates = p["candidates"]

        meta = inv.get("metadata") or {}
        inv_date = parse_date(meta.get("(Date)"))
        inv_address = meta.get("(Delivery address)", "")
        inv_province = province_map.get(inv_address, "")
        inv_weight_tons = parse_weight_kg(inv.get("sku_data")) / 1000

        # Step 2
        candidates = _filter_by_date(candidates, inv_date)
        if len(candidates) == 0:
            manual_review.append({"id": inv["id"], "reason": REASON_DATE_OUT_OF_WINDOW})
            continue
        if len(candidates) == 1:
            matched[candidates[0]["id"]].append(inv["id"])
            continue

        # Step 3a: province (skip if LLM unavailable)
        candidates, province_signal = _filter_by_province(
            candidates, inv_province, province_map
        )
        if province_signal:
            if len(candidates) == 0:
                manual_review.append(
                    {"id": inv["id"], "reason": REASON_PROVINCE_MISMATCH}
                )
                continue
            if len(candidates) == 1:
                matched[candidates[0]["id"]].append(inv["id"])
                continue

        # Step 3b: token overlap
        candidates = _filter_by_token_overlap(candidates, inv_address)
        if len(candidates) == 1:
            matched[candidates[0]["id"]].append(inv["id"])
            continue

        # Step 4: weight tiebreak
        candidates = _tiebreak_by_weight(candidates, inv_weight_tons)
        if len(candidates) == 1:
            matched[candidates[0]["id"]].append(inv["id"])
        else:
            manual_review.append({"id": inv["id"], "reason": REASON_UNCLEAR_DETAILS})

    return {
        "matches": dict(matched),
        "unmatched_invoice_ids": unmatched,
        "manual_review": manual_review,
        "stats": {
            "total_invoices": len(invoices),
            "invoices_with_plate": len(with_plate) + len(unmatched),
            "invoices_without_plate": sum(
                1 for inv in invoices if not normalize_plate(inv.get("truck_plate"))
            ),
            "matched_invoices": sum(len(v) for v in matched.values()),
            "unmatched_invoices": len(unmatched),
            "manual_review_invoices": len(manual_review),
            "deliveries_with_match": len(matched),
            "deliveries_without_match": len(deliveries) - len(matched),
        },
    }
