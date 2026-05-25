"""
Find students present in the source Excel but missing from the database,
then export them (plus their family members) as an Excel file ready for bulk import.

Usage:
    DATABASE_URL=<neon-url> python scripts/find_missing_students.py path/to/new_excel.xlsx
"""

import sys
import os
from datetime import date, datetime
import pandas as pd
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("Set DATABASE_URL environment variable first.")

if len(sys.argv) < 2:
    sys.exit("Usage: python scripts/find_missing_students.py path/to/new_excel.xlsx")

excel_path = sys.argv[1]


def clean_nid(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(12) if s.isdigit() and len(s) < 12 else s


def clean_sid(val):
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
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


CERT_MAP = {
    "bachelors": "Bachelors", "bachelor": "Bachelors",
    "masters": "Masters", "master": "Masters",
    "doctorate": "Doctorate", "phd": "Doctorate",
    "certificate": "Certificate",
    "specialization": "Specialization", "specialisation": "Specialization",
}


def map_certificate(raw) -> str:
    if not raw:
        return "Bachelors"
    return CERT_MAP.get(str(raw).strip().lower(), "Bachelors")


# ── Read Excel ────────────────────────────────────────────────────────────────
print(f"Reading Excel: {excel_path}")
df_students = pd.read_excel(excel_path, sheet_name="student data")
df_family   = pd.read_excel(excel_path, sheet_name="family data")
df_enrich   = pd.read_excel(excel_path, sheet_name="more student data")

df_students["_nid"] = df_students["national id"].apply(clean_nid)
df_students["_sid"] = df_students["student id"].apply(clean_sid)

# Deduplicate by NID (keep first)
df_students_dedup = df_students.drop_duplicates(subset="_nid", keep="first")
excel_nids = set(df_students_dedup["_nid"]) - {""}
print(f"Excel unique NIDs: {len(excel_nids)}")

# ── Query DB for existing NIDs ────────────────────────────────────────────────
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT national_id FROM students")
db_nids = {row[0] for row in cur.fetchall()}
cur.close()
conn.close()

print(f"DB NIDs: {len(db_nids)}")

missing_nids = excel_nids - db_nids
print(f"Missing from DB: {len(missing_nids)}")

if not missing_nids:
    print("No missing students found — DB is complete.")
    sys.exit(0)

# ── Build missing students rows ───────────────────────────────────────────────
missing_students = df_students_dedup[df_students_dedup["_nid"].isin(missing_nids)].copy()

# Attach enrichment data
df_enrich["_nid"] = df_enrich["National_ID"].apply(clean_nid)
enrich_map = df_enrich.set_index("_nid")

rows_students = []
for _, row in missing_students.iterrows():
    nid = row["_nid"]
    sid = row["_sid"] or nid
    name = str(row.get("name") or "").strip()
    bday = clean_date(row.get("birthday"))
    country = str(row.get("country") or "Unknown").strip()
    gender = str(row.get("gender") or "").strip()

    enr = enrich_map.loc[nid] if nid in enrich_map.index else None
    if enr is not None:
        certificate   = map_certificate(enr.get("Certificate"))
        specialization = str(enr.get("Specialization") or "").strip()
        study_country  = str(enr.get("Study_Country_Standardized") or country).strip()
        start_date     = clean_date(enr.get("Start_Date"))
        end_date       = clean_date(enr.get("End_Date"))
        decision_no    = str(enr.get("Scholarship decision number") or "N/A").strip()
        duration_months       = enr.get("Duration_Months")
        months_already_spent  = enr.get("Months_Already_Spent")
        remaining_months      = enr.get("Remaining_Study_Months")
    else:
        certificate = "Bachelors"
        specialization = ""
        study_country = country
        start_date = None
        end_date = None
        decision_no = "N/A"
        duration_months = None
        months_already_spent = None
        remaining_months = None

    rows_students.append({
        "national_id":            nid,
        "student_id":             sid,
        "name":                   name,
        "birthday":               bday.isoformat() if bday else "",
        "gender":                 gender,
        "country":                study_country,
        "certificate":            certificate,
        "specialization":         specialization,
        "decision_no":            decision_no,
        "start_date":             start_date.isoformat() if start_date else "",
        "end_date":               end_date.isoformat() if end_date else "",
        "duration_months":        duration_months,
        "months_already_spent":   months_already_spent,
        "remaining_study_months": remaining_months,
    })

df_out_students = pd.DataFrame(rows_students)

# ── Build matching family rows ────────────────────────────────────────────────
df_family["_sid"] = df_family["student id"].apply(clean_sid)
missing_sids = set(missing_students["_sid"].tolist())
df_out_family = df_family[df_family["_sid"].isin(missing_sids)].copy()
df_out_family = df_out_family.rename(columns={
    "name": "name", "national id": "national_id",
    "student id": "student_id", "birthday": "birthday",
    "relation": "relationship", "gender": "gender",
})

# ── Write output Excel ────────────────────────────────────────────────────────
out_path = f"missing_students_{date.today().isoformat()}.xlsx"
with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
    df_out_students.to_excel(writer, sheet_name="missing_students", index=False)
    df_out_family.to_excel(writer, sheet_name="missing_family", index=False)

print(f"\nExported {len(df_out_students)} missing students and {len(df_out_family)} family members.")
print(f"Output: {out_path}")
print("\nMissing student NIDs:")
for nid in sorted(missing_nids):
    name = missing_students[missing_students["_nid"] == nid]["name"].values[0]
    print(f"  {nid}  {name}")
