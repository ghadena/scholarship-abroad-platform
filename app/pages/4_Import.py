"""
Import page — bulk-load students from an Excel or CSV file.

v1 imports students only. Accompaniments are out of scope.
For accompaniments via a second sheet (linked by national_id), that is a
planned follow-up — contact the admin to enable it.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from io import BytesIO

import pandas as pd
import streamlit as st

from app import database as db
from app.auth import login, logout, require_role
from app.importer import load_excel, map_columns, validate_import, import_rows

st.set_page_config(page_title="Import", page_icon="📥", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin", "entry")

SCHEMA_FIELDS = [
    "national_id", "student_id", "full_name", "birthday",
    "country_abroad", "study_level", "study_field",
    "start_date", "end_date", "decision_no",
    "phone", "email",
]

st.title("Bulk Import Students")
st.info(
    "**v1 — Students only.** Accompaniments are not imported here. "
    "Upload a single sheet with one student per row."
)

uploaded = st.file_uploader("Upload Excel (.xlsx) or CSV (.csv)", type=["xlsx", "csv"])

if uploaded:
    raw_df = load_excel(uploaded.read())
    st.subheader("Preview (first 10 rows)")
    st.dataframe(raw_df.head(10), use_container_width=True)

    source_cols = ["(skip)"] + list(raw_df.columns)

    st.subheader("Column Mapping")
    st.markdown(
        "For each required schema field, select the matching column from your file. "
        "Fields marked \\* are required."
    )

    mapping = {}
    required = {"national_id", "student_id", "full_name", "birthday",
                "country_abroad", "study_level", "study_field",
                "start_date", "end_date", "decision_no"}

    cols_left, cols_right = st.columns(2)
    for i, field in enumerate(SCHEMA_FIELDS):
        label = f"{field} *" if field in required else field
        # Try to auto-select a matching source column
        default_idx = next(
            (j + 1 for j, c in enumerate(raw_df.columns) if c == field), 0
        )
        col = (cols_left if i % 2 == 0 else cols_right).selectbox(
            label, source_cols, index=default_idx, key=f"map_{field}"
        )
        if col != "(skip)":
            mapping[col] = field

    if st.button("Validate"):
        if not mapping:
            st.error("Please map at least the required columns before validating.")
        else:
            mapped_df = map_columns(raw_df, mapping)
            valid_df, rejected_df = validate_import(mapped_df)
            st.session_state["valid_df"]    = valid_df
            st.session_state["rejected_df"] = rejected_df

            st.success(f"Valid rows: **{len(valid_df)}**")
            if not rejected_df.empty:
                st.warning(f"Rejected rows: **{len(rejected_df)}**")
                st.dataframe(rejected_df, use_container_width=True)

                buf = BytesIO()
                rejected_df.to_excel(buf, index=False)
                st.download_button(
                    "Download rejected rows (.xlsx)",
                    data=buf.getvalue(),
                    file_name="rejected_rows.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    if st.session_state.get("valid_df") is not None and not st.session_state["valid_df"].empty:
        st.markdown("---")
        if st.button("Import valid rows", type="primary"):
            valid_df = st.session_state["valid_df"]
            with db.get_conn() as conn:
                result = import_rows(conn, valid_df)
                from app.duplicates import flag_soft_duplicates
                flag_soft_duplicates(conn)

            st.success(
                f"Import complete: **{result['inserted']}** inserted, "
                f"**{result['skipped_duplicates']}** skipped (already exist)."
            )
            st.session_state.pop("valid_df", None)
            st.session_state.pop("rejected_df", None)
