"""Dashboard page — KPI metrics and interactive Plotly charts."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from app import database as db
from app.auth import login, logout, require_role

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin", "entry")

st.title("Dashboard")
df = db.fetch_full_students_df()
acc_df = db.fetch_accompaniments_df()

if df.empty:
    st.info("No data yet — add records first.")
else:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Students", len(df))
    k2.metric("Total Accompaniments", len(acc_df))
    k3.metric("Countries", df["country_abroad"].nunique())
    k4.metric("Flagged Records", int(df["birthday_flag"].sum()))

    st.markdown("---")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(
            df["country_abroad"].value_counts().reset_index(),
            x="country_abroad", y="count",
            labels={"country_abroad": "Country", "count": "Students"},
            title="Students by Country",
        )
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.pie(df, names="study_level", title="Study Level Distribution", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        gender_df = df["gender"].value_counts().reset_index()
        fig = px.pie(gender_df, names="gender", values="count", title="Gender Split")
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        df["start_date"] = pd.to_datetime(df["start_date"])
        df["quarter"] = df["start_date"].dt.to_period("Q").astype(str)
        q_df = df["quarter"].value_counts().sort_index().reset_index()
        fig = px.line(
            q_df, x="quarter", y="count", markers=True,
            title="Students Starting per Quarter",
            labels={"quarter": "Quarter", "count": "Students"},
        )
        st.plotly_chart(fig, use_container_width=True)

    if "duplicate_flag" in df.columns and df["duplicate_flag"].sum() > 0:
        st.warning(
            f"{int(df['duplicate_flag'].sum())} record(s) are flagged as potential duplicates. "
            "Review them on the Admin page."
        )
