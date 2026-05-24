"""Tests for app/validation.py"""

import pytest
from datetime import date

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.validation import (
    is_valid_nid_format,
    derive_gender,
    derive_birth_year,
    verify_birthday,
    validate_student_form,
)


# ── NID format ────────────────────────────────────────────────────────────────

def test_valid_nid():
    assert is_valid_nid_format("123456789012") is True


def test_nid_too_short():
    assert is_valid_nid_format("12345") is False


def test_nid_too_long():
    assert is_valid_nid_format("1234567890123") is False


def test_nid_with_letters():
    assert is_valid_nid_format("12345678901A") is False


def test_nid_empty():
    assert is_valid_nid_format("") is False


# ── Gender derivation ─────────────────────────────────────────────────────────

def test_derive_gender_male():
    assert derive_gender("119950112345") == "Male"


def test_derive_gender_female():
    assert derive_gender("219950112345") == "Female"


def test_derive_gender_unknown_digit():
    assert derive_gender("319950112345") is None


def test_derive_gender_invalid_nid():
    assert derive_gender("invalid") is None


# ── Birth year derivation ─────────────────────────────────────────────────────

def test_derive_birth_year():
    assert derive_birth_year("119950112345") == 1995


def test_derive_birth_year_invalid():
    assert derive_birth_year("short") is None


# ── Birthday flag logic ───────────────────────────────────────────────────────

def test_verify_birthday_match():
    # NID encodes 1995, birthday is 1995 → True (no flag)
    assert verify_birthday("119950112345", date(1995, 6, 1)) is True


def test_verify_birthday_mismatch():
    # NID encodes 1995, birthday is 1990 → False (will be flagged)
    assert verify_birthday("119950112345", date(1990, 6, 1)) is False


def test_verify_birthday_invalid_nid():
    assert verify_birthday("bad", date(1995, 1, 1)) is False


# ── validate_student_form ─────────────────────────────────────────────────────

def _good_form(**overrides):
    base = {
        "full_name": "Ali Hassan",
        "national_id": "119950112345",
        "student_id": "STU001",
        "birthday": date(1995, 1, 1),
        "country_abroad": "UK",
        "study_level": "Masters",
        "study_field": "Engineering",
        "start_date": date(2024, 9, 1),
        "end_date": date(2026, 6, 30),
        "decision_no": "DEC-001",
    }
    base.update(overrides)
    return base


def test_valid_form_no_errors():
    assert validate_student_form(_good_form()) == []


def test_missing_full_name():
    errs = validate_student_form(_good_form(full_name=""))
    assert any("Full name" in e for e in errs)


def test_missing_national_id():
    errs = validate_student_form(_good_form(national_id=""))
    assert any("National ID" in e for e in errs)


def test_invalid_nid_format():
    errs = validate_student_form(_good_form(national_id="123"))
    assert any("12 digits" in e for e in errs)


def test_end_before_start():
    errs = validate_student_form(
        _good_form(start_date=date(2025, 1, 1), end_date=date(2024, 1, 1))
    )
    assert any("End date" in e for e in errs)


def test_bad_email():
    errs = validate_student_form(_good_form(email="notanemail"))
    assert any("Email" in e for e in errs)
