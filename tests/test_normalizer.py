from datetime import datetime

import pytest

from pipeline.normalizer import normalize_plate, parse_date, parse_weight_kg, tokenize


class TestNormalizePlate:
    def test_removes_dash_dot_space(self):
        assert normalize_plate("62F-003.94") == "62F00394"

    def test_uppercase(self):
        assert normalize_plate("62f-003.94") == "62F00394"

    def test_none_returns_none(self):
        assert normalize_plate(None) is None

    def test_empty_returns_none(self):
        assert normalize_plate("") is None

    def test_already_normalized(self):
        assert normalize_plate("49H01936") == "49H01936"


class TestParseDate:
    def test_dd_mm_yyyy(self):
        assert parse_date("04/07/2025") == datetime(2025, 7, 4)

    def test_yyyy_mm_dd(self):
        assert parse_date("2025-07-04") == datetime(2025, 7, 4)

    def test_none_returns_none(self):
        assert parse_date(None) is None

    def test_invalid_returns_none(self):
        assert parse_date("not-a-date") is None


class TestParseWeightKg:
    def test_normal(self):
        assert parse_weight_kg({"net_weight": 5000}) == pytest.approx(5000)

    def test_nan_returns_zero(self):
        assert parse_weight_kg({"net_weight": float("nan")}) == 0.0

    def test_none_dict_returns_zero(self):
        assert parse_weight_kg(None) == 0.0

    def test_nan_string_returns_zero(self):
        assert parse_weight_kg({"net_weight": "NaN"}) == 0.0


class TestTokenize:
    def test_basic(self):
        tokens = tokenize("Đường Trần Khánh Dư, Phường 8, Đà Lạt")
        assert "trần" in tokens
        assert "khánh" in tokens
        assert "phường" in tokens

    def test_strips_punctuation(self):
        tokens = tokenize("Big C, Lý Thường Kiệt")
        assert "big" in tokens
        assert "kiệt" in tokens

    def test_empty_returns_empty_set(self):
        assert tokenize("") == set()
        assert tokenize(None) == set()
