"""Tests for CPV code matching."""

from app.cpv_codes import CPV_CODES, CPV_CODE_SET, matches_cpv


def test_cpv_codes_count():
    assert len(CPV_CODES) == 36


def test_exact_match():
    assert matches_cpv("72000000") is True
    assert matches_cpv("48000000") is True
    assert matches_cpv("30200000") is True


def test_match_with_check_digit():
    assert matches_cpv("72000000-5") is True
    assert matches_cpv("48000000-8") is True


def test_child_code_matches_parent():
    # 72413000 starts with "724" -> parent 72400000 ends with "00000"
    assert matches_cpv("72413000-8") is True


def test_unrelated_code_no_match():
    assert matches_cpv("45000000-7") is False
    assert matches_cpv("99999999") is False


def test_code_set_matches_dict():
    assert CPV_CODE_SET == set(CPV_CODES.keys())
