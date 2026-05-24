"""Tests for app/duplicates.py"""

import sqlite3
import pytest

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.duplicates import find_duplicates, flag_soft_duplicates, auto_remove_exact_duplicates


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def conn():
    """In-memory SQLite database with the students table (minimal schema)."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE students (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            national_id  TEXT NOT NULL,
            student_id   TEXT NOT NULL,
            full_name    TEXT NOT NULL,
            birthday     DATE NOT NULL,
            gender       TEXT,
            birthday_flag INTEGER NOT NULL DEFAULT 0,
            phone        TEXT,
            email        TEXT,
            country_abroad TEXT NOT NULL DEFAULT 'UK',
            study_level  TEXT NOT NULL DEFAULT 'Masters',
            study_field  TEXT NOT NULL DEFAULT 'Engineering',
            start_date   DATE NOT NULL DEFAULT '2024-01-01',
            end_date     DATE NOT NULL DEFAULT '2026-01-01',
            decision_no  TEXT NOT NULL DEFAULT 'DEC-001',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            duplicate_flag   INTEGER NOT NULL DEFAULT 0,
            duplicate_reason TEXT
        );
    """)
    c.commit()
    yield c
    c.close()


def _insert(conn, national_id, student_id, full_name, birthday="1995-01-01"):
    conn.execute(
        "INSERT INTO students (national_id, student_id, full_name, birthday) VALUES (?,?,?,?)",
        (national_id, student_id, full_name, birthday),
    )
    conn.commit()


# ── find_duplicates ───────────────────────────────────────────────────────────

def test_no_duplicates(conn):
    _insert(conn, "100000000001", "S001", "Alice")
    _insert(conn, "200000000002", "S002", "Bob")
    result = find_duplicates(conn)
    assert result["exact"] == []
    assert result["soft"] == []


def test_exact_duplicate_detected(conn):
    _insert(conn, "100000000001", "S001", "Alice", "1995-01-01")
    _insert(conn, "100000000001", "S001", "Alice", "1995-01-01")
    result = find_duplicates(conn)
    assert len(result["exact"]) == 1
    assert result["soft"] == []


def test_soft_duplicate_by_national_id(conn):
    _insert(conn, "100000000001", "S001", "Alice", "1995-01-01")
    _insert(conn, "100000000001", "S002", "Bob",   "1990-05-10")
    result = find_duplicates(conn)
    assert result["exact"] == []
    assert len(result["soft"]) == 1
    assert result["soft"][0]["matched_on"] == "national_id"


def test_soft_duplicate_by_name(conn):
    _insert(conn, "100000000001", "S001", "Alice", "1995-01-01")
    _insert(conn, "200000000002", "S002", "alice", "1990-05-10")
    result = find_duplicates(conn)
    # lowercase match on full_name
    assert len(result["soft"]) == 1


# ── flag_soft_duplicates ──────────────────────────────────────────────────────

def test_flag_soft_duplicates_sets_flag(conn):
    _insert(conn, "100000000001", "S001", "Alice", "1995-01-01")
    _insert(conn, "100000000001", "S002", "Bob",   "1990-05-10")
    flag_soft_duplicates(conn)
    flags = [r[0] for r in conn.execute("SELECT duplicate_flag FROM students").fetchall()]
    assert all(f == 1 for f in flags)


def test_flag_clears_after_no_duplicates(conn):
    _insert(conn, "100000000001", "S001", "Alice", "1995-01-01")
    flag_soft_duplicates(conn)
    flags = [r[0] for r in conn.execute("SELECT duplicate_flag FROM students").fetchall()]
    assert all(f == 0 for f in flags)


# ── auto_remove_exact_duplicates ──────────────────────────────────────────────

def test_auto_remove_keeps_lowest_id(conn):
    _insert(conn, "100000000001", "S001", "Alice", "1995-01-01")
    _insert(conn, "100000000001", "S001", "Alice", "1995-01-01")
    removed = auto_remove_exact_duplicates(conn)
    assert removed == 1
    remaining = conn.execute("SELECT id FROM students").fetchall()
    assert len(remaining) == 1
    assert remaining[0][0] == 1  # lowest id kept


def test_auto_remove_no_exact_dupes(conn):
    _insert(conn, "100000000001", "S001", "Alice")
    _insert(conn, "200000000002", "S002", "Bob")
    assert auto_remove_exact_duplicates(conn) == 0
