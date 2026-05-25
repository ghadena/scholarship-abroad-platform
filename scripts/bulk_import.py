"""
One-shot bulk import from new_excel.xlsx into Neon Postgres.

Sheets used:
  'student data'      -> students table
  'family data'       -> accompaniments table  (linked by student_id)
  'more student data' -> student_enrichment table (linked by national_id)

Run with:
  DATABASE_URL="postgresql://..." python3 scripts/bulk_import.py /path/to/file.xlsx
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from app.database import get_conn, init_db, _USE_POSTGRES
from app.validation import derive_gender, verify_birthday
from datetime import date, datetime


RELATIONSHIP_MAP = {
    "spouse": "Spouse", "wife": "Spouse", "husband": "Spouse",
    "son": "Son",
    "daughter": "Daughter",
    "sibling": "Sibling", "brother": "Sibling", "sister": "Sibling",
    "father": "Spouse", "mother": "Spouse",
    "رب العائلة": "Spouse", "زوجة": "Spouse", "زوج": "Spouse",
    "ابن": "Son", "ابنة": "Daughter", "أخ": "Sibling", "أخت": "Sibling",
    "student": None, "موفد": None,   # the student themselves — skip entirely
}

CERT_MAP = {
    "bachelors": "Bachelors", "bachelor": "Bachelors",
    "masters": "Masters", "master": "Masters",
    "doctorate": "Doctorate", "phd": "Doctorate",
    "certificate": "Certificate",
    "specialization": "Specialization", "specialisation": "Specialization",
}


def clean_nid(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    # Remove float suffix
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(12) if s.isdigit() and len(s) < 12 else s


def clean_sid(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if s not in ("nan", "None", "") else ""


def clean_date(val):
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


def map_relationship(raw) -> str | None:
    if not raw:
        return "Unknown"
    key = str(raw).strip().lower()
    # Returns None for "student"/"موفد" (skip those rows entirely)
    # Returns "Unknown" for anything not in the map
    return RELATIONSHIP_MAP.get(key, "Unknown")


def map_certificate(raw) -> str:
    if not raw:
        return "Bachelors"
    key = str(raw).strip().lower()
    return CERT_MAP.get(key, "Bachelors")


# ── per-row savepoint helper for Postgres ────────────────────────────────────

def _pg_insert_safe(conn, sql, params):
    """Run a single INSERT wrapped in a savepoint so errors don't kill the tx."""
    cur = conn.cursor()
    cur.execute("SAVEPOINT sp")
    try:
        cur.execute(sql, params)
        cur.execute("RELEASE SAVEPOINT sp")
        return cur
    except Exception as e:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
        raise e


# ── import functions ──────────────────────────────────────────────────────────

def import_students(conn, df: pd.DataFrame):
    inserted = flagged = skipped = 0
    nid_to_id = {}
    seen_nids = {}  # nid -> row index of first occurrence, to detect within-file duplicates

    for idx, row in df.iterrows():
        nid = clean_nid(row.get("national id") or row.get("national_id"))
        sid = clean_sid(row.get("student id") or row.get("student_id"))
        full_name = str(row.get("name") or "").strip()
        birthday = clean_date(row.get("birthday"))
        country = str(row.get("country") or "").strip() or None
        gender_raw = str(row.get("gender") or "").strip()
        gender = gender_raw if gender_raw in ("Male", "Female") else derive_gender(nid)
        birthday_flag = 0 if (birthday and verify_birthday(nid, birthday)) else 1

        if not nid or not full_name or not birthday:
            print(f"  SKIP (missing required field): nid={nid!r} name={full_name!r}")
            skipped += 1
            continue

        # Use nid as fallback student_id if missing
        if not sid:
            sid = nid

        # Detect within-file duplicate NIDs — flag both
        dup_flag = 0
        dup_reason = None
        if nid in seen_nids:
            dup_flag = 1
            dup_reason = f"NID appears more than once in source file (also row {seen_nids[nid]})"
            print(f"  FLAGGED duplicate NID in file: {nid} — {full_name}")
        else:
            seen_nids[nid] = idx

        bday_str = birthday.isoformat()

        # Check if student_id is already taken by a DIFFERENT student — append ? to make unique
        cur = conn.cursor()
        cur.execute("SELECT national_id FROM students WHERE student_id = %s", (sid,))
        existing_sid = cur.fetchone()
        if existing_sid and existing_sid[0] != nid:
            sid = f"{sid}?"
            dup_flag = 1
            conflict_note = f"student_id conflict (original taken by {existing_sid[0]})"
            dup_reason = f"{dup_reason}; {conflict_note}" if dup_reason else conflict_note
            print(f"  FLAGGED student_id conflict: {nid} — {full_name} → sid set to {sid!r}")

        try:
            cur.execute("SAVEPOINT sp")
            try:
                cur.execute(
                    """INSERT INTO students
                       (national_id, student_id, full_name, birthday, gender, birthday_flag,
                        country_abroad, study_level, study_field, start_date, end_date, decision_no,
                        duplicate_flag, duplicate_reason)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (national_id) DO UPDATE SET
                           duplicate_flag   = 1,
                           duplicate_reason = EXCLUDED.duplicate_reason""",
                    (nid, sid, full_name, bday_str, gender, birthday_flag,
                     country or "Unknown", "Bachelors", "N/A",
                     "2020-01-01", "2026-01-01", "N/A",
                     dup_flag, dup_reason),
                )
                cur.execute("RELEASE SAVEPOINT sp")
                cur.execute("SELECT id FROM students WHERE national_id = %s", (nid,))
                r = cur.fetchone()
                if r:
                    nid_to_id[nid] = r[0]
                if dup_flag:
                    flagged += 1
                else:
                    inserted += 1
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                raise e
        except Exception as e:
            print(f"  Student error ({nid}): {e}")
            skipped += 1

    return inserted, flagged, skipped, nid_to_id


def build_sid_to_dbid(conn) -> dict:
    """Return {student_id_str: db_pk} for all students."""
    if _USE_POSTGRES:
        cur = conn.cursor()
        cur.execute("SELECT id, student_id FROM students")
        return {str(r[1]): r[0] for r in cur.fetchall()}
    else:
        cur = conn.execute("SELECT id, student_id FROM students")
        return {str(r["student_id"]): r["id"] for r in cur.fetchall()}


def import_family(conn, df: pd.DataFrame, sid_to_dbid: dict):
    inserted = skipped = 0

    for _, row in df.iterrows():
        raw_sid = clean_sid(row.get("student id") or row.get("student_id"))
        db_id = sid_to_dbid.get(raw_sid)
        if not db_id:
            skipped += 1
            continue

        nid = clean_nid(row.get("national id") or row.get("national_id"))
        full_name = str(row.get("name") or "").strip()
        birthday = clean_date(row.get("birthday"))
        rel_raw = str(row.get("relation") or row.get("relationship") or "").strip()
        rel = map_relationship(rel_raw)
        gender_raw = str(row.get("gender") or "").strip()
        gender = gender_raw if gender_raw in ("Male", "Female") else derive_gender(nid)
        birthday_flag = 0 if (birthday and verify_birthday(nid, birthday)) else 1

        if rel is None or not full_name or not birthday:
            skipped += 1
            continue

        # Pad nid to 12 digits if missing/short; family NIDs can be malformed
        if not nid or len(nid) != 12:
            nid = (nid or "0").zfill(12)

        bday_str = birthday.isoformat()

        try:
            if _USE_POSTGRES:
                _pg_insert_safe(conn,
                    """INSERT INTO accompaniments
                       (student_id_fk, full_name, national_id, birthday, relationship, gender, birthday_flag)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (db_id, full_name, nid, bday_str, rel, gender, birthday_flag),
                )
            else:
                conn.execute(
                    """INSERT INTO accompaniments
                       (student_id_fk, full_name, national_id, birthday, relationship, gender, birthday_flag)
                       VALUES (?,?,?,?,?,?,?)""",
                    (db_id, full_name, nid, bday_str, rel, gender, birthday_flag),
                )
            inserted += 1
        except Exception as e:
            print(f"  Family skip ({full_name}): {e}")
            skipped += 1

    return inserted, skipped


def import_enrichment(conn, df: pd.DataFrame):
    inserted = skipped = 0

    for _, row in df.iterrows():
        nid = clean_nid(row.get("National_ID"))
        decision_no = str(row.get("Scholarship decision number") or "").strip() or None
        certificate = map_certificate(row.get("Certificate"))
        specialization = str(row.get("Specialization") or "").strip() or None
        country = str(row.get("Study_Country_Standardized") or "").strip() or None
        start_date = clean_date(row.get("Start_Date"))
        end_date = clean_date(row.get("End_Date"))
        duration = int(row.get("Duration_Months") or 0) or None
        spent = int(row.get("Months_Already_Spent") or 0) or None
        # remaining_study_months is NOT stored — always recalculated from end_date - today at runtime

        if not nid:
            skipped += 1
            continue

        sd = start_date.isoformat() if start_date else None
        ed = end_date.isoformat() if end_date else None

        try:
            if _USE_POSTGRES:
                _pg_insert_safe(conn,
                    """INSERT INTO student_enrichment
                       (national_id, decision_no, certificate, specialization, study_country,
                        start_date, end_date, duration_months, months_already_spent)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (national_id) DO UPDATE SET
                           decision_no=EXCLUDED.decision_no,
                           certificate=EXCLUDED.certificate,
                           specialization=EXCLUDED.specialization,
                           study_country=EXCLUDED.study_country,
                           start_date=EXCLUDED.start_date,
                           end_date=EXCLUDED.end_date,
                           duration_months=EXCLUDED.duration_months,
                           months_already_spent=EXCLUDED.months_already_spent""",
                    (nid, decision_no, certificate, specialization, country,
                     sd, ed, duration, spent),
                )
            else:
                conn.execute(
                    """INSERT OR REPLACE INTO student_enrichment
                       (national_id, decision_no, certificate, specialization, study_country,
                        start_date, end_date, duration_months, months_already_spent)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (nid, decision_no, certificate, specialization, country,
                     sd, ed, duration, spent),
                )
            inserted += 1
        except Exception as e:
            print(f"  Enrichment skip ({nid}): {e}")
            skipped += 1

    return inserted, skipped


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/bulk_import.py /path/to/file.xlsx")
        sys.exit(1)

    path = sys.argv[1]
    print(f"Loading {path} ...")
    xl = pd.ExcelFile(path)

    students_df = xl.parse("student data")
    family_df   = xl.parse("family data")
    enriched_df = xl.parse("more student data")

    print(f"  Students: {len(students_df)} | Family: {len(family_df)} | Enriched: {len(enriched_df)}")

    print("\nInitialising schema ...")
    init_db()

    print("Importing students ...")
    with get_conn() as conn:
        s_ins, s_flag, s_skip, _ = import_students(conn, students_df)
        sid_to_dbid = build_sid_to_dbid(conn)
    print(f"  Inserted: {s_ins}  |  Flagged (dup NID): {s_flag}  |  Skipped: {s_skip}")

    print("Importing family members ...")
    with get_conn() as conn:
        f_ins, f_skip = import_family(conn, family_df, sid_to_dbid)
    print(f"  Inserted: {f_ins}  |  Skipped: {f_skip}")

    print("Importing enrichment data ...")
    with get_conn() as conn:
        e_ins, e_skip = import_enrichment(conn, enriched_df)
    print(f"  Inserted: {e_ins}  |  Skipped: {e_skip}")

    print("\nDone.")


if __name__ == "__main__":
    main()
