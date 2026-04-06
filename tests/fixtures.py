"""
Test fixtures extracted from large_set.json / large_set_vat.json.
Only fields used by the matcher are kept.
"""


def _delivery(id_, plate, pickup, dropoff, weight, dropoff_name="", dropoff_desc=""):
    return {
        "id": id_,
        "pickup_date": pickup,
        "dropoff_date": dropoff,
        "weight": weight,
        "computed_data": {"truck": {"plate": plate}},
        "dropoff_location": {"name": dropoff_name, "description": dropoff_desc},
    }


def _invoice(id_, plate, date, weight_kg, delivery_addr=""):
    return {
        "id": id_,
        "truck_plate": plate,
        "metadata": {"(Date)": date, "(Delivery address)": delivery_addr},
        "sku_data": {"net_weight": weight_kg},
    }


# ── Scenario A: unique plate, 1 delivery ──────────────────────────────────────
# plate 49H01936, 2 deliveries different dates → date filter resolves

DEL_67131 = _delivery(
    67131,
    "49H-019.36",
    "2025-07-04",
    "2025-07-05",
    15.28,
    dropoff_name="CÔNG TY TNHH NGỌC TRƯƠNG",
    dropoff_desc="26 Đường Trần Khánh Dư, Phường 8, Thành phố Đà Lạt, Lâm Đồng",
)
DEL_66787 = _delivery(
    66787,
    "49H-019.36",
    "2025-07-01",
    "2025-07-02",
    15.64,
    dropoff_name="Mai Hoa",
    dropoff_desc="705 QL20, Liên Nghĩa, Đức Trọng, Lâm Đồng, Việt Nam",
)

# Invoice matching 67131 by date (04/07) and address
INV_67131_A = _invoice(
    10001,
    "49H-019.36",
    "04/07/2025",
    14600,
    delivery_addr="SỐ 26-28 TRẦN KHÁNH DƯ, PHƯỜNG 8, THÀNH PHỐ ĐÀ LẠT, TỈNH LÂM ĐỒNG",
)
# Invoice matching 66787 by date (01/07) and address
INV_66787_A = _invoice(
    10002,
    "49H-019.36",
    "01/07/2025",
    14750,
    delivery_addr="SỐ 705, QUỐC LỘ 20, THỊ TRẤN LIÊN NGHĨA, HUYỆN ĐỨC TRỌNG, TỈNH LÂM ĐỒNG",
)

# ── Scenario B: duplicate plate, same date, different dropoff ─────────────────
# plate 50H67882 — Big C Quảng Ngãi vs Tuan Viet

DEL_66985 = _delivery(
    66985,
    "50H-678.82",
    "2025-07-02",
    "2025-07-03",
    None,
    dropoff_name="Big C Quảng Ngãi",
    dropoff_desc="KFC Big C Quảng Ngãi, Lý Thường Kiệt, Nghĩa Chánh, Thành phố Quảng Ngãi",
)
DEL_66984 = _delivery(
    66984,
    "50H-678.82",
    "2025-07-02",
    "2025-07-03",
    None,
    dropoff_name="Tuan Viet",
    dropoff_desc="Tịnh ấn Tây, Sơn Tịnh, Quảng Ngãi, Vietnam",
)

INV_66985_A = _invoice(
    10003,
    "50H-678.82",
    "02/07/2025",
    3500,
    delivery_addr="TTTM Siêu thị Big C, Đường Lý Thường Kiệt, Phường Nghĩa Chánh, Quảng Ngãi",
)

# ── Scenario C: no plate ──────────────────────────────────────────────────────
INV_NO_PLATE = _invoice(10004, None, "02/07/2025", 5000, "Some address")

# ── Scenario D: plate exists, no delivery match ───────────────────────────────
INV_UNKNOWN_PLATE = _invoice(10005, "99Z-999.99", "02/07/2025", 5000, "Some address")

# ── Scenario E: date outside window ──────────────────────────────────────────
INV_DATE_FAIL = _invoice(
    10006,
    "49H-019.36",
    "10/07/2025",
    14600,  # way outside window
    delivery_addr="SỐ 26-28 TRẦN KHÁNH DƯ, PHƯỜNG 8, ĐÀ LẠT",
)
