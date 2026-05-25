"""
Import the missing_students_YYYY-MM-DD.xlsx file produced by find_missing_students.py.

Sheet layout:
  'missing_students'  -> students + enrichment (combined columns)
  'missing_family'    -> accompaniments

Usage:
    DATABASE_URL=<neon-url> python scripts/import_missing_students.py missing_students_2026-05-25.xlsx
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from app.database import get_conn, _USE_POSTGRES
from scripts.bulk_import import (
    clean_nid, clean_sid, clean_date, map_certificate, map_relationship,
    derive_gender, verify_birthday, import_family, build_sid_to_dbid,
    _pg_insert_safe,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("Set DATABASE_URL environment variable first.")

if len(sys.argv) < 2:
    sys.exit("Usage: python scripts/import_missing_students.py missing_students_YYYY-MM-DD.xlsx")

path = sys.argv[1]
xl = pd.ExcelFile(path)
students_df = xl.parse("missing_students")
family_df   = xl.parse("missing_family")

print(f"File: {path}")
print(f"Students to import: {len(students_df)}")
print(f"Family to import:   {len(family_df)}")


def import_missing_students(conn, df):
    """Insert students + their enrichment data from the combined sheet."""
    inserted = skipped = 0
    nid_to_id = {}

    for _, row in df.iterrows():
        nid = clean_nid(row.get("national_id"))
        sid = clean_sid(row.get("student_id")) or nid
        full_name = str(row.get("name") or "").strip()
        birthday  = clean_date(row.get("birthday"))
        country   = str(row.get("country") or "Unknown").strip()
        gender_raw = str(row.get("gender") or "").strip()
        gender = gender_raw if gender_raw in ("Male", "Female") else derive_gender(nid)
        birthday_flag = 0 if (birthday and verify_birthday(nid, birthday)) else 1

        if not nid or not full_name or not birthday:
            print(f"  SKIP (missing required field): nid={nid!r} name={full_name!r}")
            skipped += 1
            continue

        bday_str = birthday.isoformat()

        # If student_id is already taken by another student, fall back to NID
        # and flag the record so it can be reviewed
        cur = conn.cursor()
        cur.execute("SELECT id FROM students WHERE student_id = %s AND national_id != %s", (sid, nid))
        sid_taken = cur.fetchone()
        if sid_taken:
            sid = nid  # use NID as student_id — it's guaranteed unique
            duplicate_flag = 1
            duplicate_reason = f"student_id {row.get('student_id')} already assigned to another student"
        else:
            duplicate_flag = 0
            duplicate_reason = None

        # Insert student row (placeholder study_level — enrichment holds the real value)
        cur.execute("SAVEPOINT sp_stu")
        try:
            cur.execute(
                """INSERT INTO students
                   (national_id, student_id, full_name, birthday, gender, birthday_flag,
                    country_abroad, study_level, study_field, start_date, end_date, decision_no,
                    duplicate_flag, duplicate_reason)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (national_id) DO NOTHING""",
                (nid, sid, full_name, bday_str, gender, birthday_flag,
                 country, "Bachelors", "N/A",
                 row.get("start_date") or "2020-01-01",
                 row.get("end_date")   or "2026-01-01",
                 str(row.get("decision_no") or "N/A").strip(),
                 duplicate_flag, duplicate_reason),
            )
            cur.execute("RELEASE SAVEPOINT sp_stu")
            if cur.rowcount == 1:
                cur.execute("SELECT id FROM students WHERE national_id = %s", (nid,))
                r = cur.fetchone()
                if r:
                    nid_to_id[nid] = r[0]
                flag_note = " [flagged: student_id conflict]" if duplicate_flag else ""
                print(f"  OK: {nid} {full_name}{flag_note}")
                inserted += 1
            else:
                print(f"  DUPLICATE (already in DB): {nid} {full_name}")
                cur.execute("SELECT id FROM students WHERE national_id = %s", (nid,))
                r = cur.fetchone()
                if r:
                    nid_to_id[nid] = r[0]
                skipped += 1
        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT sp_stu")
            print(f"  ERROR student ({nid}): {e}")
            skipped += 1
            continue

        # Insert enrichment row
        certificate    = map_certificate(row.get("certificate"))
        specialization = str(row.get("specialization") or "").strip()
        start_date     = clean_date(row.get("start_date"))
        end_date       = clean_date(row.get("end_date"))
        decision_no    = str(row.get("decision_no") or "").strip()
        duration       = int(row.get("duration_months") or 0)
        spent          = int(row.get("months_already_spent") or 0)
        remaining      = int(row.get("remaining_study_months") or 0)

        sd = start_date.isoformat() if start_date else None
        ed = end_date.isoformat() if end_date else None

        cur.execute("SAVEPOINT sp_enr")
        try:
            cur.execute(
                """INSERT INTO student_enrichment
                   (national_id, decision_no, certificate, specialization, study_country,
                    start_date, end_date, duration_months, months_already_spent, remaining_study_months)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (national_id) DO UPDATE SET
                       certificate=EXCLUDED.certificate,
                       specialization=EXCLUDED.specialization,
                       study_country=EXCLUDED.study_country,
                       start_date=EXCLUDED.start_date,
                       end_date=EXCLUDED.end_date,
                       duration_months=EXCLUDED.duration_months,
                       months_already_spent=EXCLUDED.months_already_spent,
                       remaining_study_months=EXCLUDED.remaining_study_months""",
                (nid, decision_no, certificate, specialization, country,
                 sd, ed, duration, spent, remaining),
            )
            cur.execute("RELEASE SAVEPOINT sp_enr")
        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT sp_enr")
            print(f"  WARN enrichment ({nid}): {e}")

    return inserted, skipped, nid_to_id


print("\nImporting students + enrichment...")
with get_conn() as conn:
    s_ins, s_skip, nid_to_id = import_missing_students(conn, students_df)
    sid_to_dbid = build_sid_to_dbid(conn)
print(f"  Inserted: {s_ins}  |  Skipped/duplicate: {s_skip}")

# Map family sheet: student_id column links to student_id in students table
# Rename to match what import_family expects
family_df = family_df.rename(columns={"student_id": "student id", "national_id": "national id",
                                       "relationship": "relation"})
print("\nImporting family members...")
with get_conn() as conn:
    f_ins, f_skip = import_family(conn, family_df, sid_to_dbid)
print(f"  Inserted: {f_ins}  |  Skipped: {f_skip}")

print("\nDone. Refresh the app to see updated counts.")
