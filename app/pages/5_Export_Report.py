"""Export & Report page — CSV/Excel download and quarterly PDF report."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from app import database as db
from app.auth import login, logout, require_role
from app.report import build_quarterly_report

st.set_page_config(page_title="Export & Report", page_icon="📄", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin", "entry")

st.title("Export & Quarterly Report")
df = db.fetch_students_df()
acc_df = db.fetch_accompaniments_df()

if df.empty:
    st.info("Nothing to export yet.")
else:
    st.subheader("Data Export")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download Students CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"students_{date.today()}.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download Accompaniments CSV",
            acc_df.to_csv(index=False).encode("utf-8"),
            file_name=f"accompaniments_{date.today()}.csv",
            mime="text/csv",
        )
    with c2:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Students", index=False)
            acc_df.to_excel(writer, sheet_name="Accompaniments", index=False)
        st.download_button(
            "Download Combined Excel",
            buf.getvalue(),
            file_name=f"scholarship_export_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("---")
    st.subheader("Quarterly Report (PDF)")
    years = sorted(pd.to_datetime(df["start_date"]).dt.year.unique(), reverse=True)
    rc1, rc2 = st.columns(2)
    with rc1:
        year = st.selectbox("Year", years)
    with rc2:
        quarter = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"])

    if st.button("Generate Quarterly Report", type="primary"):
        pdf_bytes = build_quarterly_report(df, acc_df, int(year), quarter)
        st.success("Report generated.")
        st.download_button(
            "Download PDF Report",
            pdf_bytes,
            file_name=f"scholarship_report_{year}_{quarter}.pdf",
            mime="application/pdf",
        )
