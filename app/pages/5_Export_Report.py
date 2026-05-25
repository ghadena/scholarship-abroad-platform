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

df     = db.fetch_full_students_df()
acc_df = db.fetch_accompaniments_df()
enr_df = db.fetch_enrichment_df()

if df.empty:
    st.info("Nothing to export yet.")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
st.subheader("Filters")
fc1, fc2, fc3 = st.columns(3)

with fc1:
    selected_countries = st.multiselect(
        "Country",
        options=sorted(df["country_abroad"].dropna().unique().tolist()),
        placeholder="All countries",
    )
with fc2:
    selected_genders = st.multiselect(
        "Gender",
        options=sorted(df["gender"].dropna().unique().tolist()),
        placeholder="All genders",
    )
with fc3:
    selected_levels = st.multiselect(
        "Study Level",
        options=["Bachelors", "Masters", "Doctorate", "Certificate", "Specialization"],
        placeholder="All levels",
    )

# Apply filters
filtered_df = df.copy()
if selected_countries:
    filtered_df = filtered_df[filtered_df["country_abroad"].isin(selected_countries)]
if selected_genders:
    filtered_df = filtered_df[filtered_df["gender"].isin(selected_genders)]
if selected_levels:
    filtered_df = filtered_df[filtered_df["study_level"].isin(selected_levels)]

st.caption(f"Showing **{len(filtered_df):,}** of **{len(df):,}** students")

# Derive matching acc / enr subsets
filtered_student_ids = set(filtered_df["id"].tolist())
filtered_nids        = set(filtered_df["national_id"].tolist())

filtered_acc_df = (
    acc_df[acc_df["student_id_fk"].isin(filtered_student_ids)]
    if "student_id_fk" in acc_df.columns else acc_df
)
filtered_enr_df = (
    enr_df[enr_df["national_id"].isin(filtered_nids)]
    if "national_id" in enr_df.columns else enr_df
)

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
        filtered_df.to_excel(writer,     sheet_name="Students",       index=False)
        filtered_acc_df.to_excel(writer, sheet_name="Accompaniments", index=False)
        filtered_enr_df.to_excel(writer, sheet_name="Enrichment",     index=False)
    st.download_button(
        "Download Combined Excel",
        buf.getvalue(),
        file_name=f"scholarship_export_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.markdown("---")

# ── Executive Report (PDF) ────────────────────────────────────────────────────
st.subheader("Executive Report (PDF)")
st.caption(
    "Reports are generated from the filtered data above. "
    "Use the checkbox below to control whether already-ended students are included."
)

exclude_overdue = st.checkbox(
    "Exclude students whose study period has already ended (recommended)",
    value=True,
    key="excl_overdue",
)

st.markdown("**Optional sections**")
oc1, oc2 = st.columns(2)
with oc1:
    include_ending_soon = st.checkbox(
        "Students Ending Within 6 Months table",
        value=False,
        key="incl_ending_soon",
    )
    include_study_level = st.checkbox(
        "Study Level & Field Analysis section",
        value=False,
        key="incl_study_level",
    )
with oc2:
    include_long_study = st.checkbox(
        "Long-Study Outliers section (5+ years abroad)",
        value=False,
        key="incl_long_study",
    )
    include_large_family = st.checkbox(
        "Large Families section (8+ members)",
        value=False,
        key="incl_large_family",
    )

def _filter_label():
    parts = []
    if selected_countries:
        parts.append("_".join(c.replace(" ", "-") for c in selected_countries[:2]))
    if selected_genders:
        parts.append("_".join(g.lower() for g in selected_genders))
    if selected_levels:
        parts.append("_".join(l.lower() for l in selected_levels))
    return ("_" + "_".join(parts)) if parts else ""

rep1, rep2 = st.columns(2)

with rep1:
    st.markdown("**English report**")
    if st.button("Generate English Report", type="primary", key="gen_en"):
        with st.spinner("Building English report…"):
            pdf_en = build_executive_report(
                filtered_df.copy(), filtered_acc_df.copy(), filtered_enr_df.copy(),
                arabic=False,
                exclude_overdue=exclude_overdue,
                include_ending_soon_table=include_ending_soon,
                include_study_level_section=include_study_level,
                include_long_study_section=include_long_study,
                include_large_family_section=include_large_family,
            )
        st.session_state["pdf_en"] = pdf_en
        st.success("English report ready.")

    if "pdf_en" in st.session_state:
        st.download_button(
            "Download English PDF",
            st.session_state["pdf_en"],
            file_name=f"scholarship_report_EN{_filter_label()}_{date.today()}.pdf",
            mime="application/pdf",
            key="dl_en",
        )

with rep2:
    st.markdown("**التقرير العربي**")
    if st.button("إنشاء التقرير العربي", type="primary", key="gen_ar"):
        with st.spinner("جارٍ إنشاء التقرير العربي…"):
            pdf_ar = build_executive_report(
                filtered_df.copy(), filtered_acc_df.copy(), filtered_enr_df.copy(),
                arabic=True,
                exclude_overdue=exclude_overdue,
                include_ending_soon_table=include_ending_soon,
                include_study_level_section=include_study_level,
                include_long_study_section=include_long_study,
                include_large_family_section=include_large_family,
            )
        st.session_state["pdf_ar"] = pdf_ar
        st.success("التقرير العربي جاهز.")

    if "pdf_ar" in st.session_state:
        st.download_button(
            "تحميل التقرير العربي PDF",
            st.session_state["pdf_ar"],
            file_name=f"scholarship_report_AR{_filter_label()}_{date.today()}.pdf",
            mime="application/pdf",
            key="dl_ar",
        )
