"""
Scholarship Abroad Platform — entry point.

This file is the landing / welcome page. All other pages live under app/pages/
and are auto-discovered by Streamlit's multipage routing.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from app import database as db
from app.auth import login, logout

st.set_page_config(
    page_title="Scholarship Abroad Platform",
    page_icon="🎓",
    layout="wide",
)

db.init_db()

# ---------- Auth ----------
authenticated, name, username = login()
if not authenticated:
    st.stop()

logout()

# ---------- Welcome ----------
st.title("🎓 Scholarship Abroad Platform")
st.markdown(f"Welcome, **{name}**.")
st.markdown("---")

st.markdown(
    """
    Use the sidebar to navigate between pages:

    | Page | Description |
    |------|-------------|
    | **Data Entry** | Add a new student and their accompaniments |
    | **Records** | Browse, filter, and request deletion of records |
    | **Dashboard** | Interactive KPI charts |
    | **Import** | Bulk-import students from Excel or CSV |
    | **Export & Report** | Download data or generate a quarterly PDF |
    | **Admin** *(admin only)* | Approve deletion requests, manage duplicates |
    """
)

df = db.fetch_students_df()
acc_df = db.fetch_accompaniments_df()

c1, c2, c3 = st.columns(3)
c1.metric("Total Students", len(df))
c2.metric("Total Accompaniments", len(acc_df))
if not df.empty:
    c3.metric("Flagged Records", int(df["birthday_flag"].sum()))
