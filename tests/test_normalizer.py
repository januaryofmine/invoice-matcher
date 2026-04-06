import pytest
from datetime import datetime

from matcher.normalizer import normalize_plate, parse_date, parse_weight_kg


class TestNormalizePlate:
    def test_removes_dashes_and_dots(self):
        assert normalize_plate('62F-003.94') == '62F00394'

    def test_removes_spaces(self):
        assert normalize_plate('62F 003 94') == '62F00394'

    def test_uppercases(self):
        assert normalize_plate('62f-003.94') == '62F00394'

    def test_mixed_separators(self):
        assert normalize_plate('43C-158.23') == '43C15823'

    def test_none_returns_none(self):
        assert normalize_plate(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_plate('') is None

    def test_already_normalized(self):
        assert normalize_plate('62F00394') == '62F00394'


class TestParseDate:
    def test_dd_mm_yyyy(self):
        assert parse_date('03/09/2025') == datetime(2025, 9, 3)

    def test_yyyy_mm_dd(self):
        assert parse_date('2025-09-03') == datetime(2025, 9, 3)

    def test_mm_dd_yyyy(self):
        assert parse_date('09/03/2025') == datetime(2025, 3, 9)

    def test_none_returns_none(self):
        assert parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert parse_date('') is None

    def test_invalid_string_returns_none(self):
        assert parse_date('not-a-date') is None

    def test_strips_whitespace(self):
        assert parse_date('  03/09/2025  ') == datetime(2025, 9, 3)


class TestParseWeightKg:
    def test_normal_float(self):
        assert parse_weight_kg({'net_weight': 4480.112}) == pytest.approx(4480.112)

    def test_integer(self):
        assert parse_weight_kg({'net_weight': 1000}) == 1000.0

    def test_none_value(self):
        assert parse_weight_kg({'net_weight': None}) == 0.0

    def test_nan_string(self):
        assert parse_weight_kg({'net_weight': 'NaN'}) == 0.0

    def test_missing_key(self):
        assert parse_weight_kg({}) == 0.0

    def test_none_dict(self):
        assert parse_weight_kg(None) == 0.0

    def test_string_number(self):
        assert parse_weight_kg({'net_weight': '1500.5'}) == pytest.approx(1500.5)
