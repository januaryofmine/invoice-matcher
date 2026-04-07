"""
Data normalization utilities.

Design principles applied here:
  - Single Responsibility: each function does exactly one transformation.
  - Pure functions: no side effects, no I/O, no global state.
    Given the same input, always returns the same output — safe to call from
    any stage, easy to unit-test in isolation.
  - Fail-safe defaults: parsing failures return None or 0.0 rather than
    raising, so the pipeline degrades gracefully on dirty data.
"""

import re
from datetime import datetime


# ── Truck plate normalization ─────────────────────────────────────────────────


def normalize_plate(plate: str | None) -> str | None:
    """
    Collapse a raw truck plate string into a canonical lookup key.

    Vietnamese plate numbers appear in many formats in the wild:
      '62F-003.94'  →  '62F00394'
      '62F 003 94'  →  '62F00394'
      ' 51C12345 '  →  '51C12345'

    Steps:
      1. Guard: return None immediately for empty / None input.
      2. Strip all spaces, hyphens, and dots with a single regex pass.
      3. Uppercase so '62f00394' and '62F00394' map to the same key.
      4. Return None again if the result is somehow empty (edge case).
    """
    if not plate:
        return None

    # Step 2 — remove separators that have no semantic value
    normalized = re.sub(r"[\s\-\.]", "", str(plate)).upper()

    # Step 4 — guard against an all-separator input like '---'
    return normalized if normalized else None


# ── Date parsing ──────────────────────────────────────────────────────────────


def parse_date(date_str: str | None) -> datetime | None:
    """
    Parse a date string into a datetime object.

    The upstream data uses two different formats depending on its source:
      - VAT invoices:  '01/07/2025'  (DD/MM/YYYY)
      - Delivery API:  '2025-07-01'  (YYYY-MM-DD / ISO 8601)

    Steps:
      1. Guard: return None for empty / None input.
      2. Try each known format in order; return on first success.
      3. Return None if no format matches (silent — logged upstream).

    Why not raise on failure?  A single badly-formatted date should not abort
    the entire batch.  The calling code in matcher.py falls back to keeping all
    candidate deliveries when inv_date is None.
    """
    if not date_str:
        return None

    # Step 2 — iterate known formats; most invoices hit the first one
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue  # try next format

    # Step 3 — unrecognised format; caller handles None
    return None


# ── Weight parsing ────────────────────────────────────────────────────────────


def parse_weight_kg(sku_data: dict | None) -> float:
    """
    Extract net weight in kilograms from an invoice's SKU data block.

    Returns 0.0 when weight is missing or unparseable — scorer.py treats
    0.0 as "weight unknown" and skips the weight component entirely.

    Steps:
      1. Guard: return 0.0 for missing sku_data.
      2. Read net_weight key; default to 0.0 if absent.
      3. Cast to float, catching type/value errors.
      4. Reject NaN (can appear when upstream sends 'null' as a float).
    """
    if not sku_data:
        return 0.0

    try:
        # Step 2 — key may be absent or explicitly None
        raw = sku_data.get("net_weight", 0)
        result = float(raw) if raw is not None else 0.0

        # Step 4 — NaN check: float('nan') != float('nan') is True in Python
        return 0.0 if result != result else result

    except (TypeError, ValueError):
        return 0.0


def parse_weight_tons(delivery: dict) -> float | None:
    """
    Extract delivery weight in metric tons from a raw delivery record.

    Returns None (not 0.0) when weight is absent so that scorer.py can
    distinguish 'weight is zero' from 'weight is unknown'.

    Steps:
      1. Guard: return None if the 'weight' key is absent.
      2. Cast to float, catching errors.
      3. Reject NaN — return None.
    """
    raw = delivery.get("weight")
    if raw is None:
        return None  # Step 1 — key not present at all

    try:
        value = float(raw)
        # Step 3 — NaN check
        return None if value != value else value
    except (TypeError, ValueError):
        return None


# ── Text normalization ────────────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """
    Prepare a raw address string for token-based comparison.

    Steps:
      1. Guard: return empty string for falsy input.
      2. Lowercase — 'HCM' and 'hcm' should compare equal.
      3. Replace all punctuation with spaces — commas, dots, slashes etc.
         are not meaningful tokens in Vietnamese addresses.
      4. Collapse consecutive whitespace into a single space.
      5. Strip leading/trailing whitespace.
    """
    if not text:
        return ""

    text = text.lower()                          # Step 2
    text = re.sub(r"[^\w\s]", " ", text)         # Step 3
    text = re.sub(r"\s+", " ", text)             # Step 4
    return text.strip()                          # Step 5


def tokenize(text: str) -> set[str]:
    """
    Split a normalized address into a set of meaningful tokens.

    Uses a set (not list) so that downstream intersection math is O(min(|A|,|B|))
    rather than O(|A| * |B|).

    Steps:
      1. Guard: return empty set for falsy input.
      2. Normalize text (lowercase, strip punctuation).
      3. Split on whitespace.
      4. Keep only tokens longer than 1 character — single letters like 'a',
         'b', 'p' (abbreviated for 'phường') are too ambiguous to be useful.
    """
    if not text:
        return set()

    normalized = normalize_text(text)            # Step 2
    tokens = normalized.split()                  # Step 3

    # Step 4 — filter noise tokens
    return {token for token in tokens if len(token) > 1}
