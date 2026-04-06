"""
Data normalization utilities.
All functions are pure — no side effects, no I/O.
"""

import re
from datetime import datetime

# ── Plate ─────────────────────────────────────────────────────────────────────


def normalize_plate(plate: str | None) -> str | None:
    """Normalize truck plate to canonical form. '62F-003.94' → '62F00394'"""
    if not plate:
        return None
    normalized = re.sub(r"[\s\-\.]", "", str(plate)).upper()
    return normalized if normalized else None


# ── Date ──────────────────────────────────────────────────────────────────────


def parse_date(date_str: str | None) -> datetime | None:
    """Parse date string. Supports DD/MM/YYYY and YYYY-MM-DD."""
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


# ── Weight ────────────────────────────────────────────────────────────────────


def parse_weight_kg(sku_data: dict | None) -> float:
    """Extract net_weight (kg) from sku_data. Returns 0.0 on any failure."""
    if not sku_data:
        return 0.0
    try:
        w = sku_data.get("net_weight", 0)
        result = float(w) if w is not None else 0.0
        return 0.0 if result != result else result  # NaN check
    except (TypeError, ValueError):
        return 0.0


def parse_weight_tons(delivery: dict) -> float | None:
    """Extract delivery weight in tons. Returns None if missing."""
    w = delivery.get("weight")
    if w is None:
        return None
    try:
        wf = float(w)
        return None if wf != wf else wf
    except (TypeError, ValueError):
        return None


# ── Text ──────────────────────────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> set[str]:
    """Tokenize Vietnamese address into meaningful tokens."""
    if not text:
        return set()
    text = normalize_text(text)
    # Keep tokens with length > 1 (avoids single letters noise)
    return {t for t in text.split() if len(t) > 1}
