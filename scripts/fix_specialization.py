"""
Fix certificate values in student_enrichment.

The original bulk import mapped 'Specialization' -> 'Bachelors' (missing from CERT_MAP).
This script corrects those rows by re-reading the source Excel and updating the DB.

Usage:
    DATABASE_URL=<neon-url> python scripts/fix_specialization.py path/to/new_excel.xlsx
"""

import sys
import os
import pandas as pd
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("Set DATABASE_URL environment variable first.")

if len(sys.argv) < 2:
    sys.exit("Usage: python scripts/fix_specialization.py path/to/new_excel.xlsx")

excel_path = sys.argv[1]


def clean_nid(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(12) if s.isdigit() and len(s) < 12 else s


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
    key = str(raw).strip().lower()
    return CERT_MAP.get(key, "Bachelors")


print(f"Reading enrichment sheet from: {excel_path}")
df = pd.read_excel(excel_path, sheet_name="more student data")
df["_nid"] = df["National_ID"].apply(clean_nid)
df["_cert"] = df["Certificate"].apply(map_certificate)

specialization_rows = df[df["_cert"] == "Specialization"]
print(f"Found {len(specialization_rows)} Specialization rows in Excel")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Show what's currently in the DB for these NIDs
nid_list = specialization_rows["_nid"].tolist()
cur.execute(
    "SELECT national_id, certificate FROM student_enrichment WHERE national_id = ANY(%s)",
    (nid_list,)
)
db_rows = {r[0]: r[1] for r in cur.fetchall()}
print(f"\nFound {len(db_rows)} of the {len(nid_list)} NIDs in student_enrichment:")
for nid in nid_list:
    status = db_rows.get(nid, "NOT IN DB")
    print(f"  {nid}  current certificate = {status}")

print(f"\nProceeding to update {len(db_rows)} rows...")

updated = 0
not_found = []
for nid in nid_list:
    cur.execute(
        "UPDATE student_enrichment SET certificate = 'Specialization' WHERE national_id = %s",
        (nid,),
    )
    if cur.rowcount == 1:
        updated += 1
    else:
        not_found.append(nid)

conn.commit()
cur.close()
conn.close()

print(f"\nUpdated {updated} rows to 'Specialization'.")
if not_found:
    print(f"{len(not_found)} NIDs had no enrichment row (they may be in Sheet 6 — missing student profile):")
    for nid in not_found:
        print(f"  {nid}")
print("Done.")
