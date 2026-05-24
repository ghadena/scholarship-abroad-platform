"""Export & Report page — filtered CSV/Excel download and executive PDF report."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from app import database as db
from app.auth import login, logout, require_role
from app.report import build_executive_report

st.set_page_config(page_title="Export & Report", page_icon="📄", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin", "entry")

st.title("Export & Report")

df      = db.fetch_full_students_df()
acc_df  = db.fetch_accompaniments_df()
enr_df  = db.fetch_enrichment_df()

if df.empty:
    st.info("Nothing to export yet.")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
st.subheader("Filters")
fc1, fc2 = st.columns(2)

with fc1:
    countries = sorted(df["country_abroad"].dropna().unique().tolist())
    selected_countries = st.multiselect(
        "Country", options=countries, default=[], placeholder="All countries"
    )

with fc2:
    genders = sorted(df["gender"].dropna().unique().tolist())
    selected_genders = st.multiselect(
        "Gender", options=genders, default=[], placeholder="All genders"
    )

# Apply filters
filtered_df = df.copy()
if selected_countries:
    filtered_df = filtered_df[filtered_df["country_abroad"].isin(selected_countries)]
if selected_genders:
    filtered_df = filtered_df[filtered_df["gender"].isin(selected_genders)]

st.caption(f"Showing **{len(filtered_df):,}** of **{len(df):,}** students")

# Filter acc_df to match filtered students
filtered_student_ids = set(filtered_df["id"].tolist())
filtered_acc_df = acc_df[acc_df["student_id_fk"].isin(filtered_student_ids)] if "student_id_fk" in acc_df.columns else acc_df

# Filter enr_df to match filtered students
filtered_nids = set(filtered_df["national_id"].tolist())
filtered_enr_df = enr_df[enr_df["national_id"].isin(filtered_nids)] if "national_id" in enr_df.columns else enr_df

st.markdown("---")

# ── Data Export ───────────────────────────────────────────────────────────────
st.subheader("Data Export")
c1, c2 = st.columns(2)
with c1:
    st.download_button(
        "Download Students CSV",
        filtered_df.to_csv(index=False).encode("utf-8"),
        file_name=f"students_{date.today()}.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download Accompaniments CSV",
        filtered_acc_df.to_csv(index=False).encode("utf-8"),
        file_name=f"accompaniments_{date.today()}.csv",
        mime="text/csv",
    )
with c2:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        filtered_df.to_excel(writer, sheet_name="Students", index=False)
        filtered_acc_df.to_excel(writer, sheet_name="Accompaniments", index=False)
        filtered_enr_df.to_excel(writer, sheet_name="Enrichment", index=False)
    st.download_button(
        "Download Combined Excel",
        buf.getvalue(),
        file_name=f"scholarship_export_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.markdown("---")

# ── Executive Report (PDF) ────────────────────────────────────────────────────
st.subheader("Executive Report (PDF)")
st.caption("Report is generated from the filtered data above.")

if st.button("Generate Executive Report", type="primary"):
    with st.spinner("Building report…"):
        pdf_bytes = build_executive_report(filtered_df, filtered_acc_df, filtered_enr_df)
    st.success("Report generated.")
    label = "scholarship_report"
    if selected_countries:
        label += "_" + "_".join(c.replace(" ", "-") for c in selected_countries[:2])
    if selected_genders:
        label += "_" + "_".join(g.lower() for g in selected_genders)
    st.download_button(
        "Download PDF Report",
        pdf_bytes,
        file_name=f"{label}_{date.today()}.pdf",
        mime="application/pdf",
    )
