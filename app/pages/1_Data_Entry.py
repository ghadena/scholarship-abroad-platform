"""Data Entry page — add a new student and their accompaniments."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date

import streamlit as st

from app import database as db
from app import validation as v
from app.auth import login, logout, require_role

st.set_page_config(page_title="Data Entry", page_icon="📝", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin", "entry")

STUDY_LEVELS  = ["Bachelors", "Masters", "Doctorate", "Certificate"]
RELATIONSHIPS = ["Spouse", "Son", "Daughter", "Sibling"]


def preprocess_student(form: dict) -> dict:
    form["gender"] = v.derive_gender(form["national_id"])
    form["birthday_flag"] = 0 if v.verify_birthday(form["national_id"], form["birthday"]) else 1
    for k in ("birthday", "start_date", "end_date"):
        if isinstance(form.get(k), date):
            form[k] = form[k].isoformat()
    return form


def preprocess_accompaniment(acc: dict) -> dict:
    acc["gender"] = v.derive_gender(acc["national_id"])
    acc["birthday_flag"] = 0 if v.verify_birthday(acc["national_id"], acc["birthday"]) else 1
    if isinstance(acc.get("birthday"), date):
        acc["birthday"] = acc["birthday"].isoformat()
    return acc


st.title("Add New Student")

if "accompaniments" not in st.session_state:
    st.session_state.accompaniments = []

st.subheader("Student Information")
c1, c2 = st.columns(2)
with c1:
    full_name   = st.text_input("Full Name *")
    national_id = st.text_input("National ID * (12 digits)", max_chars=12)
    student_id  = st.text_input("Student ID *")
    birthday    = st.date_input("Birthday *", value=None,
                                min_value=date(1950, 1, 1), max_value=date.today())
    phone       = st.text_input("Phone Number")
    email       = st.text_input("Email")
with c2:
    country_abroad = st.text_input("Country of Study Abroad *")
    study_level    = st.selectbox("Study Level *", STUDY_LEVELS)
    study_field    = st.text_input("Study Field *")
    start_date     = st.date_input("Start Date *", value=date.today())
    end_date       = st.date_input("End Date *", value=date.today())
    decision_no    = st.text_input("Decision-to-Send No. *")

if national_id and v.is_valid_nid_format(national_id):
    derived_gender = v.derive_gender(national_id)
    derived_year   = v.derive_birth_year(national_id)
    st.info(f"Derived gender: **{derived_gender}**  |  Birth year from NID: **{derived_year}**")
    if birthday and derived_year and birthday.year != derived_year:
        st.warning(
            f"Birthday year ({birthday.year}) does not match NID year ({derived_year}). "
            "Record will be flagged for review."
        )

st.subheader("Accompaniments")
bring_acc = st.checkbox("This student will bring accompaniments")

if bring_acc:
    with st.expander("Add an accompaniment", expanded=True):
        a1, a2 = st.columns(2)
        with a1:
            acc_name = st.text_input("Accompaniment Full Name", key="acc_name")
            acc_nid  = st.text_input("Accompaniment National ID (12 digits)",
                                     max_chars=12, key="acc_nid")
        with a2:
            acc_bday = st.date_input("Accompaniment Birthday", value=None,
                                     min_value=date(1900, 1, 1), max_value=date.today(),
                                     key="acc_bday")
            acc_rel  = st.selectbox("Relationship", RELATIONSHIPS, key="acc_rel")

        if st.button("Add Accompaniment", type="secondary"):
            acc_data = {"full_name": acc_name, "national_id": acc_nid,
                        "birthday": acc_bday, "relationship": acc_rel}
            errs = v.validate_accompaniment(acc_data)
            if errs:
                for e in errs:
                    st.error(e)
            else:
                st.session_state.accompaniments.append(preprocess_accompaniment(acc_data))
                st.success(f"Added {acc_name}.")
                st.rerun()

    if st.session_state.accompaniments:
        st.markdown("**Added accompaniments:**")
        for i, a in enumerate(st.session_state.accompaniments):
            cols = st.columns([4, 2, 2, 2, 1])
            cols[0].write(a["full_name"])
            cols[1].write(a["national_id"])
            cols[2].write(a["birthday"])
            cols[3].write(a["relationship"])
            if cols[4].button("🗑", key=f"del_acc_{i}"):
                st.session_state.accompaniments.pop(i)
                st.rerun()

st.markdown("---")
if st.button("💾 Save Student Record", type="primary"):
    form = {
        "full_name": full_name, "national_id": national_id, "student_id": student_id,
        "birthday": birthday, "phone": phone, "email": email,
        "country_abroad": country_abroad, "study_level": study_level,
        "study_field": study_field, "start_date": start_date, "end_date": end_date,
        "decision_no": decision_no,
    }
    errors = v.validate_student_form(form)
    if errors:
        for e in errors:
            st.error(e)
    else:
        try:
            form = preprocess_student(form)
            new_id = db.insert_student(form, st.session_state.accompaniments)
            st.success(f"Saved. Student database ID = {new_id}.")
            if form["birthday_flag"]:
                st.warning("Record was flagged — birthday year does not match NID year.")
            st.session_state.accompaniments = []
        except Exception as ex:
            st.error(f"Database error: {ex}")
