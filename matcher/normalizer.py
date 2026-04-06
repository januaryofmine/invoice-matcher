import re
from datetime import datetime


def normalize_plate(plate: str | None) -> str | None:
    """Remove separators and uppercase. '62F-003.94' -> '62F00394'"""
    if not plate:
        return None
    return re.sub(r'[\s\-\.]', '', str(plate)).upper()


def parse_date(date_str: str | None) -> datetime | None:
    """Parse date string. Supports DD/MM/YYYY, YYYY-MM-DD, MM/DD/YYYY."""
    if not date_str:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_weight_kg(sku_data: dict | None) -> float:
    """Extract net_weight (kg) from sku_data. Returns 0.0 on any failure."""
    if not sku_data:
        return 0.0
    try:
        w = sku_data.get('net_weight', 0)
        result = float(w) if w is not None else 0.0
        return 0.0 if result != result else result  # NaN check: NaN != NaN
    except (TypeError, ValueError):
        return 0.0
