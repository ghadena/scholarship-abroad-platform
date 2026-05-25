"""Records page — browse, filter, and request deletion of student records."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from app import database as db
from app.auth import login, logout, require_role, current_username, current_role

st.set_page_config(page_title="Records", page_icon="📋", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin", "entry", "viewer")

STUDY_LEVELS = ["Bachelors", "Masters", "Doctorate", "Certificate"]

MONTHS_BANDS = {
    "1 month or less":   (None, 1),
    "Less than 6 months": (None, 6),
    "Less than 12 months": (None, 12),
    "Less than 24 months": (None, 24),
    "Over 24 months":    (24, None),
    "Already ended":     (None, 0),
}

# Columns to show in the students table, in this order.
# Flag/audit columns are moved to the end.
STUDENT_COLS = [
    "id", "full_name", "national_id", "student_id",
    "gender", "birthday", "country_abroad",
    "study_level", "study_field",
    "start_date", "end_date", "remaining_study_months",
    "duration_months", "months_already_spent",
    "decision_no", "phone", "email",
    "birthday_flag", "duplicate_flag", "duplicate_reason", "created_at",
]

# Columns to show in the accompaniments table, in this order.
ACC_COLS = [
    "student_name", "student_code",
    "full_name", "national_id", "relationship", "gender", "birthday",
    "birthday_flag", "created_at",
]

st.title("All Records")

df_raw = db.fetch_full_students_df()

if df_raw.empty:
    st.info("No students recorded yet. Add one from the Data Entry page.")
    st.stop()

# ── Recalculate remaining months dynamically (same logic as report.py) ────────
if "end_date" in df_raw.columns:
    end_dates = pd.to_datetime(df_raw["end_date"], errors="coerce")
    df_raw = df_raw.copy()
    df_raw["remaining_study_months"] = (
        (end_dates - pd.Timestamp.today()).dt.days / 30.44
    ).round().astype("Int64")

# ── FILTERS ───────────────────────────────────────────────────────────────────
st.subheader("Filters")

row1_c1, row1_c2, row1_c3 = st.columns(3)
with row1_c1:
    search = st.text_input("Search (name, national ID, student ID)", placeholder="Type to search…")
with row1_c2:
    country_filter = st.multiselect("Country", sorted(df_raw["country_abroad"].dropna().unique()))
with row1_c3:
    level_filter = st.multiselect("Study Level", STUDY_LEVELS)

row2_c1, row2_c2, row2_c3, row2_c4 = st.columns(4)
with row2_c1:
    gender_filter = st.multiselect("Gender", ["Male", "Female"])
with row2_c2:
    months_filter = st.selectbox("Remaining study (months)", ["All"] + list(MONTHS_BANDS.keys()))
with row2_c3:
    only_flagged = st.checkbox("Only birthday-flagged")
    only_dupes   = st.checkbox("Only duplicate-flagged")

# ── APPLY FILTERS ─────────────────────────────────────────────────────────────
filtered = df_raw.copy()

if search:
    q = search.strip().lower()
    mask = (
        filtered["full_name"].str.lower().str.contains(q, na=False)
        | filtered["national_id"].astype(str).str.contains(q, na=False)
        | filtered["student_id"].astype(str).str.lower().str.contains(q, na=False)
    )
    filtered = filtered[mask]

if country_filter:
    filtered = filtered[filtered["country_abroad"].isin(country_filter)]
if level_filter:
    filtered = filtered[filtered["study_level"].isin(level_filter)]
if gender_filter:
    filtered = filtered[filtered["gender"].isin(gender_filter)]

if months_filter != "All":
    lo, hi = MONTHS_BANDS[months_filter]
    rem = pd.to_numeric(filtered["remaining_study_months"], errors="coerce")
    if lo is not None:
        rem_mask = rem > lo
    else:
        rem_mask = pd.Series(True, index=filtered.index)
    if hi is not None:
        rem_mask = rem_mask & (rem <= hi)
    filtered = filtered[rem_mask]

if only_flagged:
    filtered = filtered[filtered["birthday_flag"] == 1]
if only_dupes and "duplicate_flag" in filtered.columns:
    filtered = filtered[filtered["duplicate_flag"] == 1]

st.write(f"Showing **{len(filtered)}** of **{len(df_raw)}** students.")

# ── BUILD DISPLAY DATAFRAME ───────────────────────────────────────────────────
# Reorder columns; only include ones that actually exist in this df.
display_cols = [c for c in STUDENT_COLS if c in filtered.columns]
display = filtered[display_cols].copy()

# Add a human-readable flags column at the front for quick scanning.
if "duplicate_flag" in filtered.columns:
    def _flag_label(r):
        parts = []
        if r.get("birthday_flag") == 1:
            parts.append("⚠️ DOB mismatch")
        if r.get("duplicate_flag") == 1:
            reason = r.get("duplicate_reason") or ""
            parts.append("🔁 Duplicate" + (f" ({reason})" if reason else ""))
        return " · ".join(parts)

    display.insert(0, "Flags", filtered.apply(_flag_label, axis=1))

# ── STUDENT TABLE ─────────────────────────────────────────────────────────────
st.subheader("Students")
selection = st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ── ACCOMPANIMENTS TABLE ──────────────────────────────────────────────────────
st.subheader("Accompaniments")

acc_df_raw = db.fetch_accompaniments_df()

# Determine which student is selected (if any).
selected_rows = (selection.selection.rows if selection and selection.selection else [])
selected_student_id = None
selected_student_name = None

if selected_rows:
    idx = selected_rows[0]
    # idx is the position in `display`; map back to the filtered df
    selected_row = filtered.iloc[idx]
    selected_student_id = int(selected_row["id"])
    selected_student_name = str(selected_row["full_name"])

# Filter accompaniments: by student selection, plus propagate flag filters.
if acc_df_raw.empty:
    acc_filtered = acc_df_raw
else:
    acc_filtered = acc_df_raw.copy()

    if selected_student_id is not None:
        acc_filtered = acc_filtered[acc_filtered["student_id_fk"] == selected_student_id]
    else:
        # Propagate flag / search filters to accompaniments via student IDs in the filtered set.
        if only_flagged or only_dupes or search or country_filter or level_filter or gender_filter or months_filter != "All":
            valid_ids = set(filtered["id"].tolist())
            acc_filtered = acc_filtered[acc_filtered["student_id_fk"].isin(valid_ids)]

# Build clean display for accompaniments (drop internal FK, reorder).
if not acc_filtered.empty:
    acc_display_cols = [c for c in ACC_COLS if c in acc_filtered.columns]
    acc_display = acc_filtered[acc_display_cols].rename(columns={"student_code": "student_id"})
    if selected_student_name:
        st.caption(f"Accompaniments for **{selected_student_name}**")
    else:
        st.caption(f"Showing {len(acc_filtered)} accompaniment(s) matching current filters.")
    st.dataframe(acc_display, use_container_width=True, hide_index=True)
else:
    if selected_student_name:
        st.info(f"No accompaniments recorded for **{selected_student_name}**.")
    else:
        st.info("No accompaniments match the current filters.")

# ── DELETION TOOLS ────────────────────────────────────────────────────────────
st.subheader("Request Record Deletion")
with st.expander("Submit a deletion request"):
    del_id = st.number_input("Student database ID", min_value=1, step=1, value=1,
                             key="del_req_id")
    del_reason = st.text_area("Reason for deletion")
    if st.button("Submit Deletion Request"):
        try:
            db.create_deletion_request(int(del_id), current_username(), del_reason)
            st.success("Deletion request submitted. An admin will review it.")
        except Exception as ex:
            st.error(f"Error: {ex}")

if current_role() == "admin":
    with st.expander("Admin: delete immediately (bypasses request workflow)"):
        direct_id = st.number_input("Student database ID to delete",
                                    min_value=1, step=1, value=1, key="direct_del")
        if st.button("Delete immediately (cascade)"):
            db.delete_student(int(direct_id))
            st.success(f"Deleted student ID {direct_id}.")
            st.rerun()
