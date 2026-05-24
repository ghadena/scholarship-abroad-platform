"""
Excel / CSV bulk importer for the students table.
Accompaniments are out of scope for v1 — students only.
"""

import re
from datetime import date
from io import BytesIO

import pandas as pd

from app.validation import validate_student_form, derive_gender, verify_birthday


def _to_snake_case(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^\w]", "", name)
    return name


def load_excel(file_bytes_or_path) -> pd.DataFrame:
    """
    Read an .xlsx or .csv file.
    Accepts a file-like object (bytes/BytesIO) or a path string.
    Column names are normalised to snake_case.
    """
    if isinstance(file_bytes_or_path, (bytes, bytearray)):
        file_bytes_or_path = BytesIO(file_bytes_or_path)

    # Try to detect CSV vs Excel by trying Excel first
    try:
        df = pd.read_excel(file_bytes_or_path, dtype=str)
    except Exception:
        if hasattr(file_bytes_or_path, "seek"):
            file_bytes_or_path.seek(0)
        df = pd.read_csv(file_bytes_or_path, dtype=str)

    df.columns = [_to_snake_case(c) for c in df.columns]
    return df


def map_columns(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Rename source columns to schema columns.
    mapping = {"source_col": "schema_col", ...}
    Only columns that appear in the mapping are kept/renamed.
    """
    df = df.rename(columns=mapping)
    schema_cols = list(mapping.values())
    present = [c for c in schema_cols if c in df.columns]
    return df[present].copy()


def _coerce_row(row: dict) -> dict:
    """
    Convert string values from the spreadsheet to the types validate_student_form
    expects: dates become date objects, strings are stripped.
    """
    out = {}
    for k, v in row.items():
        if pd.isna(v) if not isinstance(v, str) else False:
            out[k] = None
            continue
        v = str(v).strip() if v is not None else ""
        if k in ("birthday", "start_date", "end_date") and v:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    from datetime import datetime
                    out[k] = datetime.strptime(v, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                out[k] = v  # leave as string; validator will catch it
        else:
            out[k] = v
    return out


def validate_import(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Validate each row using validate_student_form.
    Returns (valid_df, rejected_df) where rejected_df has an extra 'import_errors' column.
    """
    valid_rows = []
    rejected_rows = []

    for _, row in df.iterrows():
        data = _coerce_row(row.to_dict())
        errors = validate_student_form(data)
        if errors:
            row_copy = row.to_dict()
            row_copy["import_errors"] = "; ".join(errors)
            rejected_rows.append(row_copy)
        else:
            valid_rows.append(data)

    valid_df    = pd.DataFrame(valid_rows) if valid_rows    else pd.DataFrame(columns=df.columns.tolist())
    rejected_df = pd.DataFrame(rejected_rows) if rejected_rows else pd.DataFrame()
    return valid_df, rejected_df


def import_rows(conn, df_valid: pd.DataFrame) -> dict:
    """
    Insert validated rows in a single transaction.
    Derives gender and birthday_flag per row.
    Skips rows that violate UNIQUE constraints (existing records).
    Returns {"inserted": N, "skipped_duplicates": M}.
    """
    inserted = 0
    skipped = 0

    for _, row in df_valid.iterrows():
        data = _coerce_row(row.to_dict()) if not isinstance(row.to_dict().get("birthday"), date) else row.to_dict()

        # Derive fields
        nid = data.get("national_id", "")
        bday = data.get("birthday")
        data["gender"] = derive_gender(nid)
        data["birthday_flag"] = 0 if (bday and verify_birthday(nid, bday)) else 1

        # Cast dates to ISO strings for SQLite
        for k in ("birthday", "start_date", "end_date"):
            if isinstance(data.get(k), date):
                data[k] = data[k].isoformat()

        # Fill optional fields with None if missing
        for opt in ("phone", "email"):
            data.setdefault(opt, None)

        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO students (
                    national_id, student_id, full_name, birthday, gender, birthday_flag,
                    phone, email, country_abroad, study_level, study_field,
                    start_date, end_date, decision_no
                ) VALUES (
                    :national_id, :student_id, :full_name, :birthday, :gender, :birthday_flag,
                    :phone, :email, :country_abroad, :study_level, :study_field,
                    :start_date, :end_date, :decision_no
                )
                """,
                data,
            )
            if conn.execute("SELECT changes()").fetchone()[0] == 1:
                inserted += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    return {"inserted": inserted, "skipped_duplicates": skipped}
