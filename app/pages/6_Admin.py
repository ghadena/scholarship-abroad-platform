"""
Admin page — visible to admin role only.

Sections:
  1. Pending deletion requests (Approve / Reject)
  2. Soft-duplicate review (side-by-side, Dismiss)
  3. Auto-remove exact duplicates
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from app import database as db
from app.auth import login, logout, require_role, current_username
from app.duplicates import find_duplicates, auto_remove_exact_duplicates

st.set_page_config(page_title="Admin", page_icon="🔧", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin")

st.title("Admin Panel")

# =====================================================================
# SECTION 1 — DELETION REQUESTS
# =====================================================================
st.header("Pending Deletion Requests")
pending_df = db.fetch_deletion_requests_df(status="pending")

if pending_df.empty:
    st.info("No pending deletion requests.")
else:
    for _, row in pending_df.iterrows():
        with st.expander(
            f"Request #{row['id']} — {row['student_name']} ({row['student_code']}) "
            f"— by {row['requested_by']}"
        ):
            st.markdown(f"**Reason:** {row['reason'] or '(none provided)'}")
            st.markdown(f"**Requested at:** {row['created_at']}")
            col_a, col_r = st.columns(2)
            if col_a.button("Approve & Delete", key=f"approve_{row['id']}", type="primary"):
                db.resolve_deletion_request(int(row["id"]), "approved", current_username())
                st.success(f"Student {row['student_name']} deleted.")
                st.rerun()
            if col_r.button("Reject", key=f"reject_{row['id']}"):
                db.resolve_deletion_request(int(row["id"]), "rejected", current_username())
                st.info("Request rejected.")
                st.rerun()

st.markdown("---")

# =====================================================================
# SECTION 2 — SOFT DUPLICATE REVIEW
# =====================================================================
st.header("Soft Duplicate Review")
st.caption("Rows that share a national_id, student_id, or full_name but are not identical.")

with db.get_conn() as conn:
    dupes = find_duplicates(conn)

soft_list = dupes.get("soft", [])
exact_list = dupes.get("exact", [])

if not soft_list:
    st.success("No soft duplicates found.")
else:
    students_df = db.fetch_students_df()
    id_map = students_df.set_index("id").to_dict("index") if not students_df.empty else {}

    for pair in soft_list:
        id_a, id_b = pair["id_a"], pair["id_b"]
        row_a = id_map.get(id_a, {})
        row_b = id_map.get(id_b, {})
        with st.expander(
            f"IDs {id_a} vs {id_b} — matched on **{pair['matched_on']}**"
        ):
            ca, cb = st.columns(2)
            with ca:
                st.markdown(f"**ID {id_a}**")
                for field in ("full_name", "national_id", "student_id", "birthday", "country_abroad"):
                    st.text(f"{field}: {row_a.get(field, '—')}")
            with cb:
                st.markdown(f"**ID {id_b}**")
                for field in ("full_name", "national_id", "student_id", "birthday", "country_abroad"):
                    st.text(f"{field}: {row_b.get(field, '—')}")

            d1, d2, dismiss_btn = st.columns(3)
            if d1.button(f"Delete ID {id_a} (keep {id_b})", key=f"del_a_{id_a}_{id_b}"):
                db.delete_student(id_a)
                st.success(f"Deleted student {id_a}.")
                st.rerun()
            if d2.button(f"Delete ID {id_b} (keep {id_a})", key=f"del_b_{id_a}_{id_b}"):
                db.delete_student(id_b)
                st.success(f"Deleted student {id_b}.")
                st.rerun()
            if dismiss_btn.button("Dismiss (keep both)", key=f"dismiss_{id_a}_{id_b}"):
                # Clear duplicate flag for both rows without deleting
                with db.get_conn() as conn:
                    for sid in (id_a, id_b):
                        conn.execute(
                            "UPDATE students SET duplicate_flag = 0, duplicate_reason = NULL WHERE id = ?",
                            (sid,),
                        )
                st.info("Flags cleared for this pair.")
                st.rerun()

st.markdown("---")

# =====================================================================
# SECTION 3 — EXACT DUPLICATES
# =====================================================================
st.header("Exact Duplicate Cleanup")

if exact_list:
    st.warning(
        f"Found **{len(exact_list)}** exact duplicate pair(s). "
        "These share national_id, student_id, full_name, AND birthday — "
        "safe to auto-remove (lowest ID is kept)."
    )
    if st.button("Auto-remove exact duplicates", type="primary"):
        with db.get_conn() as conn:
            removed = auto_remove_exact_duplicates(conn)
        st.success(f"Removed {removed} duplicate row(s).")
        st.rerun()
else:
    st.success("No exact duplicates found.")

st.markdown("---")

# =====================================================================
# SECTION 4 — DELETION HISTORY
# =====================================================================
with st.expander("Deletion request history (all statuses)"):
    all_df = db.fetch_deletion_requests_df()
    if all_df.empty:
        st.caption("No deletion requests on record.")
    else:
        st.dataframe(all_df, use_container_width=True, hide_index=True)
