"""Records page — browse, filter, and request deletion of student records."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from app import database as db
from app.auth import login, logout, require_role, current_username, current_role

st.set_page_config(page_title="Records", page_icon="📋", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin", "entry")

STUDY_LEVELS = ["Bachelors", "Masters", "Doctorate", "Certificate"]

st.title("All Records")
df = db.fetch_students_df()

if df.empty:
    st.info("No students recorded yet. Add one from the Data Entry page.")
else:
    f1, f2, f3 = st.columns(3)
    with f1:
        country_filter = st.multiselect("Country", sorted(df["country_abroad"].unique()))
    with f2:
        level_filter = st.multiselect("Study Level", STUDY_LEVELS)
    with f3:
        only_flagged = st.checkbox("Only flagged records")
        only_dupes   = st.checkbox("Only duplicate-flagged records")

    filtered = df.copy()
    if country_filter:
        filtered = filtered[filtered["country_abroad"].isin(country_filter)]
    if level_filter:
        filtered = filtered[filtered["study_level"].isin(level_filter)]
    if only_flagged:
        filtered = filtered[filtered["birthday_flag"] == 1]
    if only_dupes and "duplicate_flag" in filtered.columns:
        filtered = filtered[filtered["duplicate_flag"] == 1]

    st.write(f"Showing **{len(filtered)}** of **{len(df)}** records.")

    # Render table with a duplicate badge column
    display = filtered.copy()
    if "duplicate_flag" in display.columns:
        display.insert(
            0,
            "Flags",
            display.apply(
                lambda r: (
                    "⚠️ Duplicate" + (f" ({r['duplicate_reason']})" if r.get("duplicate_reason") else "")
                    if r.get("duplicate_flag") == 1
                    else ""
                ),
                axis=1,
            ),
        )

    st.dataframe(display, use_container_width=True, hide_index=True)

    st.subheader("Accompaniments")
    acc_df = db.fetch_accompaniments_df()
    if acc_df.empty:
        st.caption("No accompaniments on record.")
    else:
        st.dataframe(acc_df, use_container_width=True, hide_index=True)

    # Deletion request (replaces direct delete for entry users; admin can still approve)
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

    # Admin-only: direct delete still available (bypasses request flow)
    if current_role() == "admin":
        with st.expander("Admin: delete immediately (bypasses request workflow)"):
            direct_id = st.number_input("Student database ID to delete",
                                        min_value=1, step=1, value=1, key="direct_del")
            if st.button("Delete immediately (cascade)"):
                db.delete_student(int(direct_id))
                st.success(f"Deleted student ID {direct_id}.")
                st.rerun()
