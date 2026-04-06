"""
Fixtures extracted from 20250901.json.
Only fields used by the matcher are kept — no invented data.

Scenarios covered:
  A) 72215 — unique plate, 1 invoice              → straightforward match
  B) 72212 — unique plate, 5 invoices             → all assigned to same delivery
  C) 72207 + 72208 — duplicate plate 43C-158.23   → tiebreak by weight
"""


def _make_delivery(
    id_, plate, pickup, dropoff, weight, dropoff_name="", dropoff_desc=""
):
    """Minimal delivery dict with only fields the matcher touches."""
    return {
        "id": id_,
        "pickup_date": pickup,
        "dropoff_date": dropoff,
        "weight": weight,
        "computed_data": {"truck": {"plate": plate}},
        "dropoff_location": {
            "name": dropoff_name,
            "description": dropoff_desc,
        },
    }


def _make_invoice(id_, plate, date, weight_kg, delivery_address=""):
    return {
        "id": id_,
        "truck_plate": plate,
        "metadata": {"(Date)": date, "(Delivery address)": delivery_address},
        "sku_data": {"net_weight": weight_kg},
    }


# ── Deliveries ────────────────────────────────────────────────────────────────

DELIVERY_72215 = _make_delivery(72215, "62F-003.94", "2025-09-03", "2025-09-04", 5.54)
DELIVERY_72212 = _make_delivery(72212, "63H-018.74", "2025-09-03", "2025-09-04", 14.72)
DELIVERY_72208 = _make_delivery(
    72208,
    "43C-158.23",
    "2025-09-03",
    "2025-09-04",
    9.2,
    dropoff_name="CÔNG TY TNHH THỰC PHẨM T.A.S.T.Y",
    dropoff_desc="571 Nguyễn Tất Thành, Thanh Khê, Đà Nẵng",
)
DELIVERY_72207 = _make_delivery(
    72207,
    "43C-158.23",
    "2025-09-03",
    "2025-09-05",
    9.51,
    dropoff_name="CÔNG TY TNHH GIA TRƯỜNG PHÚC",
    dropoff_desc="Lô 37 Bùi Tá Hán, Ngũ Hành Sơn, Đà Nẵng",
)

# ── Invoices ──────────────────────────────────────────────────────────────────

# Scenario A: single invoice for 72215
INVOICE_35052755 = _make_invoice(35052755, "62F-003.94", "03/09/2025", 4480.112)

# Scenario B: five invoices for 72212
INVOICE_35052984 = _make_invoice(35052984, "63H-018.74", "03/09/2025", 5499.02)
INVOICE_35052986 = _make_invoice(35052986, "63H-018.74", "03/09/2025", 1421.784)
INVOICE_35052988 = _make_invoice(35052988, "63H-018.74", "03/09/2025", 28.8)
INVOICE_35052990 = _make_invoice(35052990, "63H-018.74", "03/09/2025", 5374.792)
INVOICE_35052992 = _make_invoice(35052992, "63H-018.74", "03/09/2025", 450.0)

# Scenario C: duplicate plate, NaN weight — location tiebreak resolves correctly
# 35053243 → Ngũ Hành Sơn → 72207 (GIA TRƯỜNG PHÚC)
# 35053245 → Thanh Khê     → 72208 (T.A.S.T.Y)
INVOICE_35053243 = _make_invoice(
    35053243,
    "43C-158.23",
    "03/09/2025",
    None,
    delivery_address="LÔ 37 BÙI TÁ HÁN, PHƯỜNG NGŨ HÀNH SƠN, THÀNH PHỐ ĐÀ NẴNG, VIỆT NAM",
)
INVOICE_35053245 = _make_invoice(
    35053245,
    "43C-158.23",
    "03/09/2025",
    None,
    delivery_address="571 NGUYỄN TẤT THÀNH, PHƯỜNG THANH KHÊ, THÀNH PHỐ ĐÀ NẴNG, VIỆT NAM",
)

# ── Convenience collections ───────────────────────────────────────────────────

ALL_DELIVERIES = [DELIVERY_72215, DELIVERY_72212, DELIVERY_72208, DELIVERY_72207]

ALL_INVOICES = [
    INVOICE_35052755,
    INVOICE_35052984,
    INVOICE_35052986,
    INVOICE_35052988,
    INVOICE_35052990,
    INVOICE_35052992,
    INVOICE_35053243,
    INVOICE_35053245,
]

UNRELATED_INVOICE = _make_invoice(99999999, "99Z-999.99", "03/09/2025", 1000.0)
NO_PLATE_INVOICE = _make_invoice(88888888, None, "03/09/2025", 500.0)
OUT_OF_DATE_INVOICE = _make_invoice(
    77777777, "62F-003.94", "10/09/2025", 4480.0
)  # way outside window
