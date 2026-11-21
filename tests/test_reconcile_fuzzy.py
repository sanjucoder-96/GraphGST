"""Unit tests for the fuzzy matchers."""
from datetime import date

import pytest

from reconcile.fuzzy import (amount_close, date_close, date_delta_days,
                              is_valid_gstin, invoice_id_match, jaro_winkler,
                              normalize_id, relative_delta)


def test_normalize_id_strips_punctuation():
    assert normalize_id("INV-2024/001") == "INV2024001"
    assert normalize_id(" inv 2024 001 ") == "INV2024001"
    assert normalize_id(None) == ""


def test_jaro_winkler_bounds():
    assert 0.0 <= jaro_winkler("abc", "xyz") <= 1.0
    assert jaro_winkler("", "abc") == 0.0
    assert jaro_winkler("abc", "abc") == 1.0


def test_jaro_winkler_prefix_boost():
    a = jaro_winkler("INV2024001", "INV2024001X")
    b = jaro_winkler("INV2024001", "XINV2024001")
    # equal prefix should be preferred
    assert a > b


def test_invoice_id_match_punctuation_variants():
    assert invoice_id_match("INV-2024-001", "INV/2024/001") is True
    assert invoice_id_match("INV-2024-001", "INV 2024 001") is True
    assert invoice_id_match("INV-2024-001", "INV-2024-002") is False


def test_amount_close_absolute_tolerance():
    assert amount_close(100.0, 101.0) is True    # ±1 default
    assert amount_close(100.0, 102.0) is False


def test_amount_close_relative_tolerance():
    # 0.1 % of 1_000_000 = 1000; should accept
    assert amount_close(1_000_000.0, 1_000_500.0) is True
    assert amount_close(1_000_000.0, 1_100_000.0) is False


def test_amount_close_none_returns_false():
    assert amount_close(None, 5) is False
    assert amount_close(5, None) is False


def test_relative_delta_signed():
    assert relative_delta(110, 100) == pytest.approx(10 / 110)
    assert relative_delta(100, 110) == pytest.approx(-10 / 110)
    assert relative_delta(0, 0) == 0.0
    assert relative_delta(None, 5) is None


def test_date_close_within_3d():
    assert date_close("2024-11-01", "2024-11-04") is True
    assert date_close("2024-11-01", "2024-11-05") is False


def test_date_close_accepts_date_objects():
    assert date_close(date(2024, 11, 1), date(2024, 11, 3)) is True


def test_date_close_none_returns_false():
    assert date_close(None, "2024-11-01") is False
    assert date_close("not-a-date", "2024-11-01") is False


def test_date_delta_days_signed():
    assert date_delta_days("2024-11-05", "2024-11-01") == 4
    assert date_delta_days("2024-11-01", "2024-11-05") == -4


def test_gstin_shape_check():
    assert is_valid_gstin("27AAPFU0939F1ZV") is True
    assert is_valid_gstin("27AAPFU0939F1Z") is False   # too short
    assert is_valid_gstin("XXAAPFU0939F1ZV") is False  # non-digit state
    assert is_valid_gstin(None) is False
