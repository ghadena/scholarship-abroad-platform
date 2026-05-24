"""Tests for app/importer.py"""

import io
from datetime import date

import pandas as pd
import pytest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.importer import load_excel, map_columns, validate_import, _to_snake_case


# ── _to_snake_case ────────────────────────────────────────────────────────────

def test_snake_case_spaces():
    assert _to_snake_case("Full Name") == "full_name"


def test_snake_case_mixed():
    assert _to_snake_case("National-ID") == "national_id"


def test_snake_case_already_snake():
    assert _to_snake_case("national_id") == "national_id"


# ── load_excel (CSV path) ─────────────────────────────────────────────────────

def _make_csv(data: dict) -> bytes:
    df = pd.DataFrame(data)
    return df.to_csv(index=False).encode("utf-8")


def test_load_csv_normalises_columns():
    csv_bytes = _make_csv({"Full Name": ["Alice"], "National ID": ["100000000001"]})
    df = load_excel(csv_bytes)
    assert "full_name" in df.columns
    assert "national_id" in df.columns


def test_load_csv_returns_dataframe():
    csv_bytes = _make_csv({"col_a": [1, 2], "col_b": [3, 4]})
    df = load_excel(csv_bytes)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


# ── map_columns ───────────────────────────────────────────────────────────────

def test_map_columns_renames():
    df = pd.DataFrame({"src_name": ["Alice"], "src_nid": ["100000000001"]})
    mapping = {"src_name": "full_name", "src_nid": "national_id"}
    result = map_columns(df, mapping)
    assert list(result.columns) == ["full_name", "national_id"]


def test_map_columns_drops_unmapped():
    df = pd.DataFrame({"full_name": ["Alice"], "extra": ["x"]})
    mapping = {"full_name": "full_name"}
    result = map_columns(df, mapping)
    assert "extra" not in result.columns


# ── validate_import ───────────────────────────────────────────────────────────

def _good_row(**overrides):
    base = {
        "full_name":      "Ali Hassan",
        "national_id":    "119950112345",
        "student_id":     "STU001",
        "birthday":       "1995-01-01",
        "country_abroad": "UK",
        "study_level":    "Masters",
        "study_field":    "Engineering",
        "start_date":     "2024-09-01",
        "end_date":       "2026-06-30",
        "decision_no":    "DEC-001",
    }
    base.update(overrides)
    return base


def test_validate_import_all_valid():
    df = pd.DataFrame([_good_row(), _good_row(student_id="STU002", national_id="219950112346")])
    valid, rejected = validate_import(df)
    assert len(valid) == 2
    assert len(rejected) == 0


def test_validate_import_rejects_bad_nid():
    df = pd.DataFrame([_good_row(national_id="short")])
    valid, rejected = validate_import(df)
    assert len(valid) == 0
    assert len(rejected) == 1
    assert "import_errors" in rejected.columns


def test_validate_import_mixed():
    df = pd.DataFrame([
        _good_row(),
        _good_row(national_id="bad", student_id="STU002"),
    ])
    valid, rejected = validate_import(df)
    assert len(valid) == 1
    assert len(rejected) == 1


def test_validate_import_rejected_has_error_column():
    df = pd.DataFrame([_good_row(full_name="")])
    _, rejected = validate_import(df)
    assert "import_errors" in rejected.columns
    assert len(rejected["import_errors"].iloc[0]) > 0
