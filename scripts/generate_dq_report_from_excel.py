"""
Data Quality Report — Excel source version
===========================================
Runs the same checks as generate_data_quality_report.py but reads directly
from the source Excel file instead of the database. No DATABASE_URL needed.

Usage:
    python3 scripts/generate_dq_report_from_excel.py /path/to/new_excel.xlsx
    python3 scripts/generate_dq_report_from_excel.py /path/to/new_excel.xlsx --out report.xlsx

Expected sheets in the Excel file:
    "student data"      — students
    "family data"       — accompaniments
    "more student data" — enrichment

Sheets generated (same as the DB version):
  1  Duplicate NIDs            — same NID on 2+ student rows
  2  Missing Student IDs       — student_id == national_id (fallback) or missing
  3  Missing Family NIDs       — family members with no / malformed NID
  4  Same Name Diff NID        — family member: same name+student_ref but different NID
  5  Students without family   — students who have zero family rows (info only)
  6  Enrichment Only           — enrichment rows with no matching student NID
  7  Students Only             — students with no enrichment row
  8  Birthday Mismatch         — NID birth-year != recorded birthday year
  9  Reporting Period          — summary counts and date ranges
 10  Long Study (5yr+)         — students whose start_date <= today - 5 years
 11  Large Families (8+ mbrs)  — students with 8 or more family rows
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

TODAY = date.today()

# ── Shared style helpers (identical to DB version) ────────────────────────────

TITLE_FMT  = {"bold": True, "font_size": 13, "bg_color": "#1E3A8A", "font_color": "#FFFFFF", "border": 1}
HEADER_FMT = {"bold": True, "font_size": 9,  "bg_color": "#1E3A8A", "font_color": "#FFFFFF",
              "border": 1, "text_wrap": True, "valign": "vcenter", "align": "center"}
ODD_FMT    = {"font_size": 9, "border": 1, "bg_color": "#F0F4FF"}
EVEN_FMT   = {"font_size": 9, "border": 1, "bg_color": "#FFFFFF"}
ACTION_FMT = {"font_size": 9, "border": 1, "bg_color": "#FEF9C3", "bold": True}
SUMMARY_FMT= {"font_size": 9, "border": 1, "bg_color": "#D1FAE5"}


def _write_sheet(wb, title, arabic_title, columns, rows, action_col_idx=None, summary_rows=None):
    ws = wb.add_worksheet(title[:31])
    fmt = lambda d: wb.add_format(d)

    ws.merge_range(0, 0, 0, len(columns)-1, arabic_title, fmt(TITLE_FMT))
    ws.set_row(0, 22)

    for ci, (hdr, width) in enumerate(columns):
        ws.write(1, ci, hdr, fmt(HEADER_FMT))
        ws.set_column(ci, ci, width)
    ws.set_row(1, 30)

    for ri, row in enumerate(rows):
        bg = ODD_FMT if ri % 2 == 0 else EVEN_FMT
        for ci, val in enumerate(row):
            cell_fmt = fmt(ACTION_FMT) if ci == action_col_idx else fmt(bg)
            ws.write(2 + ri, ci, val if val is not None else "", cell_fmt)

    if summary_rows:
        base = 2 + len(rows)
        for ri, row in enumerate(summary_rows):
            for ci, val in enumerate(row):
                ws.write(base + ri, ci, val if val is not None else "", fmt(SUMMARY_FMT))

    ws.freeze_panes(2, 0)
    return ws


# ── Data loading helpers ──────────────────────────────────────────────────────

def _clean_nid(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s in ("nan", "None", ""):
        return ""
    # Handle scientific notation floats (e.g. 1.195700e+11)
    try:
        s = str(int(float(s)))
    except (ValueError, OverflowError):
        pass
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(12) if s.isdigit() and len(s) < 12 else s


def _clean_sid(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if s not in ("nan", "None", "") else ""


def _clean_date(val):
    if val is None:
        return None
    try:
        if isinstance(val, float) and pd.isna(val):
            return None
    except Exception:
        pass
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


def _derive_gender(nid: str) -> str:
    if nid and len(nid) >= 1:
        d = nid[0]
        if d == "1":
            return "Male"
        if d == "2":
            return "Female"
    return ""


def _nid_year(nid: str):
    if nid and len(nid) >= 5 and nid[1:5].isdigit():
        return int(nid[1:5])
    return None


def load_excel(path: str):
    xl = pd.ExcelFile(path)
    students_raw  = xl.parse("student data")
    family_raw    = xl.parse("family data")
    enriched_raw  = xl.parse("more student data")

    # ── Normalise students ────────────────────────────────────────────────────
    stu = pd.DataFrame()
    stu["national_id"] = students_raw.get("national id", students_raw.get("national_id", pd.Series())).apply(_clean_nid)
    stu["student_id"]  = students_raw.get("student id",  students_raw.get("student_id",  pd.Series())).apply(_clean_sid)
    stu["full_name"]   = students_raw.get("name", pd.Series()).astype(str).str.strip()
    stu["birthday"]    = students_raw.get("birthday", pd.Series()).apply(_clean_date)
    stu["country"]     = students_raw.get("country", pd.Series()).astype(str).str.strip().replace("nan", "")
    stu["gender"]      = students_raw.get("gender", pd.Series()).astype(str).str.strip()
    # Derive gender from NID where missing
    stu.loc[~stu["gender"].isin(["Male","Female"]), "gender"] = \
        stu.loc[~stu["gender"].isin(["Male","Female"]), "national_id"].apply(_derive_gender)
    # Birthday flag: NID year vs birthday year
    stu["nid_year"] = stu["national_id"].apply(_nid_year)
    stu["bday_year"] = stu["birthday"].apply(lambda d: d.year if d else None)
    stu["birthday_flag"] = (
        stu["nid_year"].notna() & stu["bday_year"].notna() &
        (stu["nid_year"] != stu["bday_year"])
    ).astype(int)
    # Use NID as student_id fallback
    stu.loc[stu["student_id"] == "", "student_id"] = stu.loc[stu["student_id"] == "", "national_id"]
    stu = stu.reset_index(drop=True)

    # ── Normalise family ──────────────────────────────────────────────────────
    fam = pd.DataFrame()
    fam["student_id"]  = family_raw.get("student id", family_raw.get("student_id", pd.Series())).apply(_clean_sid)
    fam["national_id"] = family_raw.get("national id", family_raw.get("national_id", pd.Series())).apply(_clean_nid)
    fam["full_name"]   = family_raw.get("name", pd.Series()).astype(str).str.strip()
    fam["birthday"]    = family_raw.get("birthday", pd.Series()).apply(_clean_date)
    fam["relationship"]= family_raw.get("relation", family_raw.get("relationship", pd.Series())).astype(str).str.strip()
    fam["gender"]      = family_raw.get("gender", pd.Series()).astype(str).str.strip()
    fam.loc[~fam["gender"].isin(["Male","Female"]), "gender"] = \
        fam.loc[~fam["gender"].isin(["Male","Female"]), "national_id"].apply(_derive_gender)
    fam["nid_year"] = fam["national_id"].apply(_nid_year)
    fam["bday_year"] = fam["birthday"].apply(lambda d: d.year if d else None)
    fam["birthday_flag"] = (
        fam["nid_year"].notna() & fam["bday_year"].notna() &
        (fam["nid_year"] != fam["bday_year"])
    ).astype(int)
    fam = fam.reset_index(drop=True)

    # ── Normalise enrichment ──────────────────────────────────────────────────
    enr = pd.DataFrame()
    enr["national_id"]    = enriched_raw.get("National_ID", pd.Series()).apply(_clean_nid)
    enr["decision_no"]    = enriched_raw.get("Scholarship decision number", pd.Series()).astype(str).str.strip()
    enr["certificate"]    = enriched_raw.get("Certificate", pd.Series()).astype(str).str.strip()
    enr["specialization"] = enriched_raw.get("Specialization", pd.Series()).astype(str).str.strip()
    enr["study_country"]  = enriched_raw.get("Study_Country_Standardized", pd.Series()).astype(str).str.strip()
    enr["start_date"]     = enriched_raw.get("Start_Date", pd.Series()).apply(_clean_date)
    enr["end_date"]       = enriched_raw.get("End_Date", pd.Series()).apply(_clean_date)
    enr["duration_months"]= enriched_raw.get("Duration_Months", pd.Series())
    enr["months_spent"]   = enriched_raw.get("Months_Already_Spent", pd.Series())
    enr = enr[enr["national_id"] != ""].reset_index(drop=True)

    return stu, fam, enr


# ── Sheet generators ──────────────────────────────────────────────────────────

def sheet1_duplicate_nids(stu, wb):
    dup_nids = stu[stu["national_id"] != ""].groupby("national_id").filter(lambda g: len(g) > 1)
    cols = [
        ("الاسم", 30), ("الرقم الوطني", 18), ("رقم القيد", 14),
        ("تاريخ الميلاد", 14), ("الدولة", 18), ("الجنس", 10),
        ("الإجراء المطلوب", 32),
    ]
    rows = []
    for _, r in dup_nids.sort_values(["national_id","full_name"]).iterrows():
        rows.append([r["full_name"], r["national_id"], r["student_id"],
                     str(r["birthday"] or ""), r["country"], r["gender"],
                     "تأكيد صاحب الرقم الوطني الصحيح"])
    _write_sheet(wb, "1 - Duplicate NIDs",
                 "الرقم الوطني مكرر — يحتاج مراجعة يدوية",
                 cols, rows, action_col_idx=6)
    return len(rows)


def sheet2_missing_student_ids(stu, wb):
    # student_id == national_id means it was used as a fallback (no real ID provided)
    mask = (stu["student_id"] == stu["national_id"]) | (stu["student_id"] == "")
    df = stu[mask].copy()
    cols = [
        ("الاسم", 30), ("الرقم الوطني", 18), ("رقم القيد الحالي", 18),
        ("تاريخ الميلاد", 14), ("الدولة", 18), ("الجنس", 10),
        ("رقم القيد الصحيح (يرجى التعبئة)", 28), ("الإجراء المطلوب", 28),
    ]
    rows = []
    for _, r in df.sort_values("full_name").iterrows():
        rows.append([r["full_name"], r["national_id"], r["student_id"],
                     str(r["birthday"] or ""), r["country"], r["gender"],
                     "", "تزويدنا برقم القيد الصحيح"])
    _write_sheet(wb, "2 - Missing Student IDs",
                 "رقم القيد مفقود — يرجى تزويدنا بالرقم الصحيح",
                 cols, rows, action_col_idx=7)
    return len(rows)


def sheet3_missing_family_nids(stu, fam, wb):
    # NID is blank, all zeros, or shorter than 12 digits
    sid_to_name = stu.set_index("student_id")["full_name"].to_dict()
    mask = (
        (fam["national_id"] == "") |
        (fam["national_id"].str.match(r"^0+$", na=True)) |
        (fam["national_id"].str.len() < 12)
    )
    df = fam[mask].copy()
    cols = [
        ("الاسم", 30), ("الرقم الوطني الحالي", 18), ("رقم قيد الطالب", 16),
        ("اسم الطالب", 26), ("تاريخ الميلاد", 14), ("صلة القرابة", 14), ("الجنس", 10),
        ("الرقم الوطني الصحيح (يرجى التعبئة)", 30), ("الإجراء المطلوب", 28),
    ]
    rows = []
    for _, r in df.sort_values("full_name").iterrows():
        rows.append([r["full_name"], r["national_id"] or "NULL",
                     r["student_id"], sid_to_name.get(r["student_id"], "—"),
                     str(r["birthday"] or ""), r["relationship"], r["gender"],
                     "", "تزويدنا بالرقم الوطني الصحيح"])
    _write_sheet(wb, "3 - Missing Family NIDs",
                 "رقم وطني مفقود لأفراد العائلة",
                 cols, rows, action_col_idx=8)
    return len(rows)


def sheet4_same_name_diff_nid(stu, fam, wb):
    sid_to_name = stu.set_index("student_id")["full_name"].to_dict()
    fam2 = fam[fam["national_id"] != ""].copy()
    fam2["name_lower"] = fam2["full_name"].str.lower().str.strip()
    # Find (student_id, name_lower) pairs with more than one distinct NID
    groups = fam2.groupby(["student_id","name_lower"])["national_id"].nunique()
    problem_keys = groups[groups > 1].index
    mask = fam2.set_index(["student_id","name_lower"]).index.isin(problem_keys)
    df = fam2[mask].copy()
    cols = [
        ("الاسم", 32), ("الرقم الوطني", 18), ("رقم قيد الطالب", 16),
        ("اسم الطالب", 26), ("تاريخ الميلاد", 14), ("صلة القرابة", 14), ("الجنس", 10),
        ("الإجراء المطلوب", 36),
    ]
    rows = []
    for _, r in df.sort_values(["full_name","national_id"]).iterrows():
        rows.append([r["full_name"], r["national_id"],
                     r["student_id"], sid_to_name.get(r["student_id"], "—"),
                     str(r["birthday"] or ""), r["relationship"], r["gender"],
                     "تأكيد الرقم الوطني وتاريخ الميلاد الصحيح"])
    _write_sheet(wb, "4 - Same Name Diff NID",
                 "نفس الاسم بأرقام وطنية مختلفة — تحتاج تأكيداً",
                 cols, rows, action_col_idx=7)
    return len(rows)


def sheet5_students_without_family(stu, fam, wb):
    """Students who have zero family rows in the family sheet."""
    student_ids_with_family = set(fam["student_id"].unique())
    df = stu[~stu["student_id"].isin(student_ids_with_family)].copy()
    cols = [
        ("الاسم الكامل", 30), ("الرقم الوطني", 18), ("رقم القيد", 14),
        ("تاريخ الميلاد", 14), ("الدولة", 18), ("الجنس", 10),
        ("ملاحظة", 36),
    ]
    rows = []
    for _, r in df.sort_values("full_name").iterrows():
        rows.append([r["full_name"], r["national_id"], r["student_id"],
                     str(r["birthday"] or ""), r["country"], r["gender"],
                     "لا يوجد أفراد عائلة مسجلون — للعلم فقط"])
    _write_sheet(wb, "5 - No Family Rows",
                 f"طلاب بدون أفراد عائلة مسجلين في ملف Excel ({len(df)} حالة) — للعلم فقط",
                 cols, rows, action_col_idx=6)
    return len(rows)


def sheet6_enrichment_only(stu, enr, wb):
    """Enrichment rows whose NID has no matching student row."""
    student_nids = set(stu["national_id"].unique())
    df = enr[~enr["national_id"].isin(student_nids)].copy()
    cols = [
        ("الرقم الوطني", 18), ("التخصص", 28), ("الشهادة", 14),
        ("دولة الدراسة", 18), ("تاريخ البداية", 14), ("تاريخ النهاية", 14),
        ("رقم القرار", 14),
        ("الاسم الكامل (يرجى التعبئة)", 26), ("تاريخ الميلاد (يرجى التعبئة)", 22),
        ("رقم القيد (يرجى التعبئة)", 20), ("الإجراء المطلوب", 28),
    ]
    rows = []
    for _, r in df.sort_values("national_id").iterrows():
        rows.append([r["national_id"], r["specialization"], r["certificate"],
                     r["study_country"], str(r["start_date"] or ""), str(r["end_date"] or ""),
                     r["decision_no"], "", "", "",
                     "إدخال البيانات الأساسية للطالب"])
    _write_sheet(wb, "6 - Enrichment Only",
                 f"بيانات بعثة بدون ملف طالب مطابق ({len(df)} حالة)",
                 cols, rows, action_col_idx=10)
    return len(rows)


def sheet7_students_only(stu, enr, wb):
    """Students with no enrichment row."""
    enr_nids = set(enr["national_id"].unique())
    df = stu[~stu["national_id"].isin(enr_nids)].copy()
    cols = [
        ("الرقم الوطني", 18), ("الاسم الكامل", 30), ("رقم القيد", 14),
        ("تاريخ الميلاد", 14), ("الدولة", 18), ("الجنس", 10),
        ("التخصص (يرجى التعبئة)", 22), ("تاريخ البداية (يرجى التعبئة)", 22),
        ("تاريخ النهاية (يرجى التعبئة)", 22), ("رقم القرار (يرجى التعبئة)", 20),
        ("الإجراء المطلوب", 30),
    ]
    rows = []
    for _, r in df.sort_values("national_id").iterrows():
        rows.append([r["national_id"], r["full_name"], r["student_id"],
                     str(r["birthday"] or ""), r["country"], r["gender"],
                     "", "", "", "",
                     "إضافة بيانات البعثة (القرار، التخصص، التواريخ)"])
    _write_sheet(wb, "7 - Students Only",
                 f"طلاب بدون بيانات بعثة ({len(df)} حالة)",
                 cols, rows, action_col_idx=10)
    return len(rows)


def sheet8_birthday_mismatch(stu, fam, wb):
    """NID birth-year (digits 2-5) does not match the recorded birthday year."""
    cols = [
        ("الفئة", 10), ("الاسم الكامل", 30), ("الرقم الوطني", 18),
        ("رقم القيد / مرجع الطالب", 18), ("تاريخ الميلاد المسجّل", 18),
        ("سنة الميلاد في الرقم الوطني", 22), ("سنة الميلاد المسجّلة", 20),
        ("الفرق (سنوات)", 16), ("الدولة", 18), ("الجنس", 10),
        ("الإجراء المطلوب", 32),
    ]
    rows = []

    s_mismatch = stu[stu["birthday_flag"] == 1].copy()
    for _, r in s_mismatch.iterrows():
        diff = abs(int(r["nid_year"]) - int(r["bday_year"])) if r["nid_year"] and r["bday_year"] else "?"
        rows.append(["Student", r["full_name"], r["national_id"], r["student_id"],
                     str(r["birthday"] or ""),
                     int(r["nid_year"]) if r["nid_year"] else "",
                     int(r["bday_year"]) if r["bday_year"] else "",
                     diff, r["country"], r["gender"],
                     "تأكيد تاريخ الميلاد الصحيح أو تصحيح الرقم الوطني"])

    f_mismatch = fam[fam["birthday_flag"] == 1].copy()
    sid_to_name = stu.set_index("student_id")["full_name"].to_dict()
    for _, r in f_mismatch.iterrows():
        diff = abs(int(r["nid_year"]) - int(r["bday_year"])) if r["nid_year"] and r["bday_year"] else "?"
        rows.append(["Family", r["full_name"], r["national_id"],
                     r["student_id"],
                     str(r["birthday"] or ""),
                     int(r["nid_year"]) if r["nid_year"] else "",
                     int(r["bday_year"]) if r["bday_year"] else "",
                     diff, "", r["gender"],
                     "تأكيد تاريخ الميلاد الصحيح أو تصحيح الرقم الوطني"])

    _write_sheet(wb, "8 - Birthday Mismatch",
                 f"تعارض بين سنة الميلاد في الرقم الوطني والتاريخ المسجّل ({len(rows)} حالة)",
                 cols, rows, action_col_idx=10)
    return len(rows)


def sheet9_reporting_period(stu, fam, enr, excel_path, wb):
    """Summary counts and date ranges derived from the Excel file."""
    ws = wb.add_worksheet("9 - Reporting Period")
    fmt = lambda d: wb.add_format(d)
    ws.set_column(0, 0, 42)
    ws.set_column(1, 1, 28)
    ws.merge_range(0, 0, 0, 1, "ملخص بيانات ملف Excel", fmt(TITLE_FMT))
    ws.set_row(0, 24)

    header_fmt = fmt({**HEADER_FMT, "align": "right", "font_size": 10})
    value_fmt  = fmt({**SUMMARY_FMT, "font_size": 10})
    note_fmt   = fmt({"font_size": 8, "italic": True, "font_color": "#64748B"})

    valid_stu = stu[stu["national_id"] != ""]
    birthday_flags = int((stu["birthday_flag"] == 1).sum())
    dup_nids = int(valid_stu.groupby("national_id").size().gt(1).sum())

    enr_starts = enr["start_date"].dropna()
    enr_ends   = enr["end_date"].dropna()
    stu_bdays  = stu["birthday"].dropna()

    summary = [
        ("تاريخ إنشاء التقرير",                   str(TODAY)),
        ("مسار ملف Excel",                        str(excel_path)),
        ("—", "—"),
        ("إجمالي صفوف 'student data'",            len(stu)),
        ("إجمالي الطلاب بعد إزالة المكرر (NID)",  len(valid_stu["national_id"].unique())),
        ("طلاب بدون رقم وطني",                    int((stu["national_id"] == "").sum())),
        ("طلاب بدون اسم",                          int((stu["full_name"].str.strip() == "").sum())),
        ("طلاب بدون تاريخ ميلاد",                 int(stu["birthday"].isna().sum())),
        ("أرقام وطنية مكررة (NIDs)",               dup_nids),
        ("سجلات بعلامة تعارض تاريخ الميلاد",      birthday_flags),
        ("—", "—"),
        ("إجمالي صفوف 'family data'",             len(fam)),
        ("أفراد عائلة بدون رقم وطني",             int((fam["national_id"] == "").sum())),
        ("أفراد عائلة بدون تاريخ ميلاد",          int(fam["birthday"].isna().sum())),
        ("—", "—"),
        ("إجمالي صفوف 'more student data'",       len(enr)),
        ("أقدم تاريخ بداية دراسة",                str(enr_starts.min()) if not enr_starts.empty else "—"),
        ("أحدث تاريخ نهاية دراسة",                str(enr_ends.max())   if not enr_ends.empty   else "—"),
        ("طلاب بتاريخ نهاية مضى (overdue)",       int((enr["end_date"].apply(lambda d: d < TODAY if d else False)).sum())),
    ]

    for ri, (label, value) in enumerate(summary):
        ws.write(ri+1, 0, label, header_fmt)
        ws.write(ri+1, 1, str(value), value_fmt)

    ws.write(len(summary)+2, 0,
             "ملاحظة: هذا التقرير مبني على بيانات ملف Excel مباشرة، وليس قاعدة البيانات.",
             note_fmt)
    ws.freeze_panes(1, 0)
    return 1


def sheet10_long_study(stu, enr, wb):
    """Students whose start_date <= today - 5 years."""
    five_years_ago = date(TODAY.year - 5, TODAY.month, TODAY.day)

    # Merge enrichment start_date onto students (enrichment wins)
    enr_sub = enr[["national_id","start_date","end_date","study_country","certificate","specialization"]].copy()
    merged = stu.merge(enr_sub, on="national_id", how="left")
    merged["eff_start"] = merged["start_date"].combine_first(pd.Series([None]*len(merged)))
    # start_date from enrichment already as date objects; fallback to None
    merged["eff_start"] = merged["start_date"]

    df = merged[
        merged["eff_start"].apply(lambda d: d is not None and d <= five_years_ago and d > date(2000,1,1))
    ].copy()
    df["years_abroad"] = df["eff_start"].apply(
        lambda d: round((TODAY - d).days / 365.25, 1) if d else None
    )
    df["country_disp"] = df["study_country"].fillna(df["country"])
    df["level_disp"]   = df["certificate"].fillna(df["gender"].apply(lambda _: ""))
    df["field_disp"]   = df["specialization"].fillna("")
    df = df.sort_values("years_abroad", ascending=False)

    cols = [
        ("الاسم الكامل", 30), ("الرقم الوطني", 18), ("رقم القيد", 14),
        ("تاريخ البداية", 14), ("تاريخ النهاية", 14), ("الدولة", 18),
        ("مستوى الدراسة", 14), ("التخصص", 26), ("الجنس", 10),
        ("سنوات في الخارج", 16), ("الإجراء المطلوب", 32),
    ]
    rows = []
    for _, r in df.iterrows():
        rows.append([r["full_name"], r["national_id"], r["student_id"],
                     str(r["eff_start"] or ""), str(r["end_date"] or ""),
                     r["country_disp"], r["level_disp"], r["field_disp"], r["gender"],
                     r["years_abroad"] or "",
                     "مراجعة وضع الطالب — مدة طويلة في الخارج"])
    _write_sheet(wb, "10 - Long Study (5yr+)",
                 f"طلاب أمضوا 5 سنوات أو أكثر في الخارج ({len(df)} حالة) — تحتاج مراجعة",
                 cols, rows, action_col_idx=10)
    return len(rows)


def sheet11_large_families(stu, fam, wb):
    """Students with 8 or more family rows."""
    fam_counts = fam.groupby("student_id").agg(
        family_count=("national_id", "count"),
        relationships=("relationship", lambda x: ", ".join(sorted(x.unique())))
    ).reset_index()
    large = fam_counts[fam_counts["family_count"] >= 8]
    merged = large.merge(stu[["student_id","national_id","full_name","country","gender"]], on="student_id", how="left")

    enr_sub = fam_counts[["student_id"]].merge(
        stu[["student_id","national_id"]], on="student_id", how="left"
    )
    # Also pull certificate + specialization from enrichment if available
    merged = merged.sort_values("family_count", ascending=False)

    cols = [
        ("الاسم الكامل", 30), ("الرقم الوطني", 18), ("رقم القيد", 14),
        ("الدولة", 18), ("الجنس", 10),
        ("عدد أفراد الأسرة", 18), ("صلات القرابة", 40),
        ("الإجراء المطلوب", 32),
    ]
    rows = []
    for _, r in merged.iterrows():
        rows.append([r["full_name"] if pd.notna(r["full_name"]) else "—",
                     r["national_id"] if pd.notna(r["national_id"]) else "—",
                     r["student_id"],
                     r["country"] if pd.notna(r["country"]) else "—",
                     r["gender"] if pd.notna(r["gender"]) else "—",
                     int(r["family_count"]), r["relationships"],
                     "مراجعة — عدد أفراد الأسرة مرتفع بشكل استثنائي"])
    _write_sheet(wb, "11 - Large Families",
                 f"طلاب لديهم 8 أفراد أسرة أو أكثر ({len(rows)} حالة) — للمراجعة الاكتوارية",
                 cols, rows, action_col_idx=7)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate data quality Excel report from a source Excel file (no DB needed)."
    )
    parser.add_argument("excel", help="Path to the source Excel file (new_excel.xlsx)")
    parser.add_argument("--out", default=f"data_quality_report_excel_{TODAY}.xlsx",
                        help="Output file path")
    args = parser.parse_args()

    if not Path(args.excel).exists():
        sys.exit(f"ERROR: File not found: {args.excel}")

    print(f"Loading {args.excel} ...")
    stu, fam, enr = load_excel(args.excel)
    print(f"  Students: {len(stu)} rows | Family: {len(fam)} rows | Enrichment: {len(enr)} rows")

    import xlsxwriter
    wb = xlsxwriter.Workbook(args.out, {"strings_to_numbers": False})

    print("Generating sheets...")
    counts = {}
    counts["1  Duplicate NIDs"]          = sheet1_duplicate_nids(stu, wb)
    counts["2  Missing Student IDs"]     = sheet2_missing_student_ids(stu, wb)
    counts["3  Missing Family NIDs"]     = sheet3_missing_family_nids(stu, fam, wb)
    counts["4  Same Name Diff NID"]      = sheet4_same_name_diff_nid(stu, fam, wb)
    counts["5  Students without family"] = sheet5_students_without_family(stu, fam, wb)
    counts["6  Enrichment Only"]         = sheet6_enrichment_only(stu, enr, wb)
    counts["7  Students Only"]           = sheet7_students_only(stu, enr, wb)
    counts["8  Birthday Mismatch"]       = sheet8_birthday_mismatch(stu, fam, wb)
    counts["9  Reporting Period"]        = sheet9_reporting_period(stu, fam, enr, args.excel, wb)
    counts["10 Long Study (5yr+)"]       = sheet10_long_study(stu, enr, wb)
    counts["11 Large Families (8+)"]     = sheet11_large_families(stu, fam, wb)

    wb.close()
    print(f"\nSaved to: {args.out}")
    print("\nIssue summary:")
    for sheet, count in counts.items():
        print(f"  {sheet:<32} {count:>4} records")


if __name__ == "__main__":
    main()
