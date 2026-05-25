"""
Executive PDF report — English and Arabic versions.
Sections: KPI banner · Geographic distribution · Population composition ·
          Age profile & family size · Study duration & time remaining ·
          Study level & field breakdown · Key findings.

Only active students (end_date >= today) are included.
"""

from datetime import date
from io import BytesIO
from pathlib import Path

import arabic_reshaper
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle, HRFlowable,
)

# ── Brand colours ─────────────────────────────────────────────────────────────
NAVY   = "#1E3A8A"
TEAL   = "#0D9488"
AMBER  = "#F59E0B"
SLATE  = "#64748B"
LIGHT  = "#F0F4FF"
WHITE  = "#FFFFFF"

W       = 15  * cm
H_CHART = 7.5 * cm
H_WIDE  = 9   * cm
H_PIE   = 7   * cm

# ── Arabic font registration ──────────────────────────────────────────────────
_FONT_DIR  = Path(__file__).parent / "fonts"
_AMIRI_TTF = _FONT_DIR / "Amiri-Regular.ttf"

_arabic_font_registered = False

def _ensure_arabic_font():
    global _arabic_font_registered
    if _arabic_font_registered:
        return
    if _AMIRI_TTF.exists():
        pdfmetrics.registerFont(TTFont("Amiri", str(_AMIRI_TTF)))
        _arabic_font_registered = True
    else:
        raise FileNotFoundError(
            f"Arabic font not found at {_AMIRI_TTF}. "
            "Run: pip install arabic-reshaper python-bidi and ensure app/fonts/Amiri-Regular.ttf exists."
        )


def _ar(text: str) -> str:
    """Reshape + bidi-reorder an Arabic string so ReportLab renders it correctly."""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


# ── Arabic translations ───────────────────────────────────────────────────────
AR = {
    # Cover
    "title":           "برنامج المنح الدراسية في الخارج",
    "subtitle":        "تقرير تنفيذي لصانعي القرار",
    "cover_body":      "يقدم هذا التقرير نظرة شاملة على المجتمع المؤمَّن في البرنامج: "
                       "{n_total} شخصاً مشمولاً في {n_countries} دولة، "
                       "يتوزعون بين {n_students} طالب و{n_family} فرداً من الأسرة. "
                       "تاريخ الإصدار: {report_date}.",
    # KPI labels
    "kpi_total":       "إجمالي المشمولين",
    "kpi_countries":   "الدول",
    "kpi_students":    "الطلاب",
    "kpi_family":      "أفراد الأسرة",
    "kpi_avg_family":  "متوسط أفراد الأسرة / طالب",
    "kpi_under18":     "نسبة من هم دون الـ 18",
    "kpi_gender":      "نسبة الإناث / الذكور",
    "kpi_top_country": "تمركز في {country}",
    # Section headings
    "geo_title":       "التوزيع الجغرافي",
    "geo_body":        "يغطي البرنامج {n_countries} دولة، غير أن التوزيع غير متكافئ. "
                       "تستحوذ أكبر ثلاث دول على غالبية المشمولين. "
                       "تمثّل {top_country} وحدها {pct_top}٪ من الطلاب.",
    "geo_rank":        "الترتيب",
    "geo_country":     "الدولة",
    "geo_students":    "الطلاب",
    "geo_family":      "أفراد الأسرة",
    "geo_total":       "الإجمالي",
    "geo_pct":         "٪ من البرنامج",
    "geo_top10":       "مجموع أعلى 10 دول",
    "geo_other":       "دول أخرى ({n})",
    "comp_title":      "تركيبة المجتمع المؤمَّن",
    "comp_body":       "يشكّل أفراد الأسرة {pct_family}٪ من إجمالي المشمولين. "
                       "يصطحب كل طالب في المتوسط {avg_family} فرداً من أسرته.",
    "comp_cat":        "الفئة",
    "comp_count":      "العدد",
    "comp_pct":        "النسبة",
    "comp_students":   "الطلاب",
    "comp_spouses":    "الأزواج",
    "comp_sons":       "الأبناء",
    "comp_daughters":  "البنات",
    "comp_siblings":   "الإخوة",
    "comp_total":      "إجمالي المشمولين",
    "age_title":       "التوزيع العمري وحجم الأسرة",
    "age_body":        "{n_under18} شخصاً ({pct_under18}٪) من المشمولين هم دون سن 18. "
                       "الشريحة العمرية 6–12 هي الأكبر عادةً.",
    "age_caption":     "الشكل: التوزيع العمري. {n_under18} شخصاً ({pct_under18}٪) دون الـ 18.",
    "fam_caption":     "الشكل: توزيع حجم الأسرة. المتوسط = {avg_family} فرداً لكل طالب.",
    "dur_title":       "مدة الدراسة والوقت المتبقي",
    "dur_body":        "يبلغ متوسط المدة المتبقية لدى الطلاب المسجلين {avg_remaining} شهراً. "
                       "{pct_ending_soon}٪ من الطلاب لديهم 12 شهراً أو أقل — "
                       "ينبغي إيلاؤهم الأولوية للتجديد أو إنهاء المنحة.",
    "dur_soon":        "طلاب ينتهي تسجيلهم خلال 6 أشهر",
    "dur_name":        "الاسم",
    "dur_nid":         "الرقم الوطني",
    "dur_country":     "الدولة",
    "dur_field":       "التخصص",
    "dur_end":         "تاريخ الانتهاء",
    "dur_months":      "الأشهر المتبقية",
    "dur_more":        "… و{n} آخرون (راجع التصدير الكامل).",
    "level_title":     "مستوى الدراسة وتحليل التخصصات",
    "level_col":       "مستوى الدراسة",
    "level_students":  "الطلاب",
    "level_pct":       "النسبة",
    "fields_title":    "أعلى التخصصات",
    "cross_title":     "التخصص × مستوى الدراسة (أعلى 10 تخصصات)",
    "cross_field":     "التخصص",
    "findings_title":  "النتائج الرئيسية",
    "steps_title":     "الخطوات الموصى بها",
    "footer":          "المصدر: قاعدة بيانات برنامج المنح الدراسية. "
                       "جميع الأرقام تعكس المجتمع المؤمَّن بتاريخ {report_date}.",
    # Chart labels
    "chart_geo_title": "أعلى 10 دول من حيث إجمالي المشمولين",
    "chart_geo_x":     "عدد المشمولين",
    "chart_students":  "الطلاب",
    "chart_family":    "أفراد الأسرة",
    "chart_person_type": "نوع الشخص",
    "chart_total":     "الإجمالي",
    "chart_age_title": "التوزيع العمري — الأطفال دون 18 مميَّزون",
    "chart_age_y":     "الأفراد",
    "chart_under18":   "دون 18 (أطفال)",
    "chart_over18":    "18 فأكثر",
    "chart_fam_title": "توزيع حجم الأسرة لكل طالب",
    "chart_fam_x":     "أفراد الأسرة لكل طالب",
    "chart_fam_y":     "عدد الطلاب",
    "chart_rem_title": "توزيع المدة المتبقية للدراسة",
    "chart_rem_y":     "الطلاب",
    "chart_rem_ended": "انتهت المنحة",
    "chart_rem_6":     "0–6 أشهر",
    "chart_rem_12":    "7–12 شهراً",
    "chart_rem_24":    "13–24 شهراً",
    "chart_rem_36":    "25–36 شهراً",
    "chart_rem_36p":   "36+ شهراً",
    "chart_level_title": "توزيع مستويات الدراسة",
    "chart_fields_title": "أعلى 15 تخصصاً",
    "chart_fields_x":  "الطلاب",
    "chart_avg":       "المتوسط: {v:.2f}",
    "chart_rem_dist":  "توزيع المدة المتبقية للدراسة",
    "findings_title":  "النتائج الرئيسية",
    "long_study_title": "فترات دراسة مطوّلة — حالات للمراجعة",
    "long_study_body":  "{n_long} طالب(ة) يقضي 5 سنوات أو أكثر في الخارج "
                        "(محتسبةً من تاريخ البداية حتى اليوم). "
                        "ينبغي مراجعة كل حالة للتأكد من استمرارية التسجيل.",
    "long_study_none":  "لا توجد حالات بفترة دراسة تتجاوز 5 سنوات في المجموعة المحددة.",
    "long_study_col_name":    "الاسم",
    "long_study_col_nid":     "الرقم الوطني",
    "long_study_col_country": "الدولة",
    "long_study_col_level":   "المستوى",
    "long_study_col_field":   "التخصص",
    "long_study_col_start":   "تاريخ البداية",
    "long_study_col_end":     "تاريخ النهاية",
    "long_study_col_years":   "سنوات في الخارج",
    "large_family_title": "الأسر الكبيرة — حالات استثنائية",
    "large_family_body":  "{n_large} طالب(ة) لديه 8 أفراد مرافقين أو أكثر. "
                          "ينبغي إخضاع هذه الأسر لاختبار ضغط لمخاطر تركّز التكاليف.",
    "large_family_none":  "لا توجد أسر تضم 8 أفراد أو أكثر في المجموعة المحددة.",
    "large_family_col_name":    "الاسم",
    "large_family_col_nid":     "الرقم الوطني",
    "large_family_col_country": "الدولة",
    "large_family_col_count":   "عدد أفراد الأسرة",
    "large_family_col_rels":    "صلات القرابة",
    "footer":          "المصدر: قاعدة بيانات برنامج المنح الدراسية. "
                       "جميع الأرقام تعكس المجتمع المؤمَّن بتاريخ {report_date}.",
}

EN = {
    "title":           "Scholarship Abroad Programme",
    "subtitle":        "Executive Report for Decision Makers",
    "cover_body":      "This report presents an at-a-glance view of the insured population: "
                       "<b>{n_total} covered people</b> spanning <b>{n_countries} countries</b>, "
                       "made up of <b>{n_students} students</b> and <b>{n_family} family members</b>. "
                       "Generated {report_date}.",
    "kpi_total":       "Total covered people",
    "kpi_countries":   "Countries reached",
    "kpi_students":    "Students",
    "kpi_family":      "Family members",
    "kpi_avg_family":  "Avg. family / student",
    "kpi_under18":     "Population under 18",
    "kpi_gender":      "Female / Male share",
    "kpi_top_country": "Concentrated in {country}",
    "geo_title":       "Geographic Distribution",
    "geo_body":        "The programme covers {n_countries} countries, but distribution is highly skewed. "
                       "The top three markets together represent the majority of all covered people. "
                       "{top_country} alone accounts for {pct_top}% of students.",
    "geo_rank":        "Rank",
    "geo_country":     "Country",
    "geo_students":    "Students",
    "geo_family":      "Family Members",
    "geo_total":       "Total",
    "geo_pct":         "% of programme",
    "geo_top10":       "Top 10 subtotal",
    "geo_other":       "Other {n} countries",
    "comp_title":      "Population Composition",
    "comp_body":       "Family members account for <b>{pct_family}%</b> of all insured people. "
                       "Each student brings on average <b>{avg_family} family members</b>.",
    "comp_cat":        "Category",
    "comp_count":      "Count",
    "comp_pct":        "% of total",
    "comp_students":   "Students",
    "comp_spouses":    "Spouses",
    "comp_sons":       "Sons",
    "comp_daughters":  "Daughters",
    "comp_siblings":   "Siblings",
    "comp_total":      "Total covered people",
    "age_title":       "Age Profile & Family Size",
    "age_body":        "<b>{n_under18} people ({pct_under18}%)</b> of the insured population are under 18. "
                       "The 6–12 band is typically the largest age cohort.",
    "age_caption":     "Figure: Age distribution. {n_under18} people ({pct_under18}%) are under 18.",
    "fam_caption":     "Figure: Family size distribution. Mean = {avg_family} dependants per student.",
    "dur_title":       "Study Duration & Time Remaining",
    "dur_body":        "Of active students, the average remaining study period is "
                       "<b>{avg_remaining} months</b>. "
                       "<b>{pct_ending_soon}%</b> have 12 months or fewer remaining — "
                       "these cases should be prioritised for renewal or exit processing.",
    "dur_soon":        "Students Ending Within 6 Months",
    "dur_name":        "Name",
    "dur_nid":         "National ID",
    "dur_country":     "Country",
    "dur_field":       "Field",
    "dur_end":         "End Date",
    "dur_months":      "Months Left",
    "dur_more":        "… and {n} more (see full export).",
    "level_title":     "Study Level & Field Analysis",
    "level_col":       "Study Level",
    "level_students":  "Students",
    "level_pct":       "% of total",
    "fields_title":    "Top Study Fields",
    "cross_title":     "Field × Study Level Breakdown (Top 10 Fields)",
    "cross_field":     "Field",
    "findings_title":  "Key Findings",
    "long_study_title": "Extended Study Periods — Cases for Review",
    "long_study_body":  "{n_long} student(s) have been abroad for 5 years or more "
                        "(measured from start date to today). These cases should be "
                        "individually reviewed to confirm active enrolment status.",
    "long_study_none":  "No students with a study period exceeding 5 years in the selected group.",
    "long_study_col_name":    "Name",
    "long_study_col_nid":     "National ID",
    "long_study_col_country": "Country",
    "long_study_col_level":   "Level",
    "long_study_col_field":   "Field",
    "long_study_col_start":   "Start Date",
    "long_study_col_end":     "End Date",
    "long_study_col_years":   "Years Abroad",
    "large_family_title": "Large Families — Actuarial Outliers",
    "large_family_body":  "{n_large} student(s) have 8 or more accompanying family members. "
                          "These households should be stress-tested for claim-cost concentration risk.",
    "large_family_none":  "No families with 8 or more members in the selected group.",
    "large_family_col_name":    "Name",
    "large_family_col_nid":     "National ID",
    "large_family_col_country": "Country",
    "large_family_col_count":   "Family Members",
    "large_family_col_rels":    "Relationships",
    "footer":          "Source: Scholarship Abroad Platform database. "
                       "All figures reflect the insured population as at {report_date}.",
    "chart_geo_title": "Top 10 Countries by Total Covered People",
    "chart_geo_x":     "Number of covered people",
    "chart_students":  "Students",
    "chart_family":    "Family members",
    "chart_person_type": "Person Type",
    "chart_total":     "Total",
    "chart_age_title": "Age Distribution — Children Under 18 Highlighted",
    "chart_age_y":     "People",
    "chart_under18":   "Under 18 (minors)",
    "chart_over18":    "18 and above",
    "chart_fam_title": "Family Size per Student — Distribution",
    "chart_fam_x":     "Family members per student",
    "chart_fam_y":     "Number of students",
    "chart_rem_title": "Remaining Study Duration Distribution",
    "chart_rem_y":     "Students",
    "chart_rem_ended": "Ended",
    "chart_rem_6":     "0–6 mo",
    "chart_rem_12":    "7–12 mo",
    "chart_rem_24":    "13–24 mo",
    "chart_rem_36":    "25–36 mo",
    "chart_rem_36p":   "36+ mo",
    "chart_level_title": "Study Level Distribution",
    "chart_fields_title": "Top 15 Study Fields",
    "chart_fields_x":  "Students",
    "chart_avg":       "Avg: {v:.2f}",
    "chart_rem_dist":  "Remaining Study Duration Distribution",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _fig_to_image(fig, width=W, height=H_CHART):
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=width, height=height)


def _style_ax(ax, title="", xlabel="", ylabel=""):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E2E8F0")
    ax.spines["bottom"].set_color("#E2E8F0")
    ax.tick_params(colors=SLATE, labelsize=8)
    ax.yaxis.grid(True, color="#E2E8F0", linewidth=0.5)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=NAVY, fontsize=10, fontweight="bold", pad=8)
    if xlabel:
        ax.set_xlabel(xlabel, color=SLATE, fontsize=8)
    if ylabel:
        ax.set_ylabel(ylabel, color=SLATE, fontsize=8)


def _ar_label(text: str) -> str:
    """Reshape Arabic text for matplotlib (which also needs bidi reordering)."""
    return get_display(arabic_reshaper.reshape(text))


# ══════════════════════════════════════════════════════════════════════════════
# CHART BUILDERS  (accept T dict so labels switch language)
# ══════════════════════════════════════════════════════════════════════════════

def _chart_geo(students_df, family_df, T, arabic=False):
    if students_df.empty:
        return None
    combined = pd.concat([
        students_df[["country_abroad"]].rename(columns={"country_abroad": "country"}).assign(type="s"),
        family_df[["country_abroad"]].rename(columns={"country_abroad": "country"}).assign(type="f"),
    ])
    by_country = combined.groupby(["country", "type"]).size().unstack(fill_value=0)
    by_country["total"] = by_country.sum(axis=1)
    top10 = by_country.nlargest(10, "total")

    fig, ax = plt.subplots(figsize=(10, 6))
    y = np.arange(len(top10))
    h = 0.4
    s_vals = top10.get("s", pd.Series(0, index=top10.index))
    f_vals = top10.get("f", pd.Series(0, index=top10.index))
    lbl_s = _ar_label(T["chart_students"]) if arabic else T["chart_students"]
    lbl_f = _ar_label(T["chart_family"])   if arabic else T["chart_family"]
    bars_s = ax.barh(y + h/2, s_vals, h, color=NAVY, label=lbl_s)
    bars_f = ax.barh(y - h/2, f_vals, h, color=TEAL, label=lbl_f)
    for bar in list(bars_s) + list(bars_f):
        w = bar.get_width()
        if w > 0:
            ax.text(w + 20, bar.get_y() + bar.get_height()/2, f"{int(w):,}",
                    va="center", fontsize=7, color=SLATE)
    ax.set_yticks(y)
    ylabels = [_ar_label(str(c)) if arabic else str(c) for c in top10.index]
    ax.set_yticklabels(ylabels, fontsize=9)
    ax.legend(fontsize=8, framealpha=0)
    title  = _ar_label(T["chart_geo_title"]) if arabic else T["chart_geo_title"]
    xlabel = _ar_label(T["chart_geo_x"])     if arabic else T["chart_geo_x"]
    _style_ax(ax, title, xlabel)
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_WIDE)


def _chart_person_type(n_students, n_family, T, arabic=False):
    if n_students + n_family == 0:
        return None
    fig, ax = plt.subplots(figsize=(5, 5))
    vals   = [n_students, n_family]
    lbl_s  = _ar_label(T["chart_students"])    if arabic else T["chart_students"]
    lbl_f  = _ar_label(T["chart_family"])      if arabic else T["chart_family"]
    labels = [lbl_s, lbl_f]
    _, _, autotexts = ax.pie(
        vals, labels=None, autopct="%1.1f%%",
        colors=[NAVY, TEAL], startangle=90,
        wedgeprops=dict(width=0.5), pctdistance=0.75,
    )
    for t in autotexts:
        t.set_fontsize(9); t.set_color("white")
    ax.legend(labels, fontsize=8, loc="lower center", framealpha=0)
    pt_title = _ar_label(T["chart_person_type"]) if arabic else T["chart_person_type"]
    ax.set_title(pt_title, color=NAVY, fontsize=10, fontweight="bold")
    total_lbl = _ar_label(T["chart_total"]) if arabic else T["chart_total"]
    ax.text(0, 0, f"{n_students+n_family:,}\n{total_lbl}",
            ha="center", va="center", fontsize=9, color=NAVY, fontweight="bold")
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_CHART)


def _chart_age(all_df, T, arabic=False):
    if all_df.empty:
        return None
    today = pd.Timestamp.today()
    all_df = all_df.copy()
    all_df["birthday"] = pd.to_datetime(all_df["birthday"], errors="coerce")
    all_df["age"] = (today - all_df["birthday"]).dt.days / 365.25
    bins   = [0, 6, 13, 18, 26, 36, 46, 56, 66, 200]
    labels = ["0–5", "6–12", "13–17", "18–25", "26–35", "36–45", "46–55", "56–65", "66+"]
    all_df["age_band"] = pd.cut(all_df["age"], bins=bins, labels=labels, right=False)
    counts = all_df["age_band"].value_counts().reindex(labels, fill_value=0)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    bar_colors = [AMBER if lbl in ("0–5","6–12","13–17") else NAVY for lbl in labels]
    xlabels = [_ar_label(l) if arabic else l for l in labels]
    bars = ax.bar(xlabels, counts.values, color=bar_colors, width=0.7)
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 10,
                f"{int(val):,}", ha="center", fontsize=7, color=SLATE)
    lbl_minor = _ar_label(T["chart_under18"]) if arabic else T["chart_under18"]
    lbl_major = _ar_label(T["chart_over18"])  if arabic else T["chart_over18"]
    legend_els = [mpatches.Patch(color=AMBER, label=lbl_minor),
                  mpatches.Patch(color=NAVY,  label=lbl_major)]
    ax.legend(handles=legend_els, fontsize=8, framealpha=0)
    title = _ar_label(T["chart_age_title"]) if arabic else T["chart_age_title"]
    ylabel = _ar_label(T["chart_age_y"])    if arabic else T["chart_age_y"]
    _style_ax(ax, title, ylabel=ylabel)
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_CHART)


def _chart_family_size(students_df, family_df, T, arabic=False):
    if students_df.empty:
        return None
    sizes = family_df.groupby("student_id_fk").size()
    students_no_family = set(students_df["id"]) - set(sizes.index)
    sizes = pd.concat([sizes, pd.Series(0, index=list(students_no_family))])
    mean_size = sizes.mean()

    fig, ax = plt.subplots(figsize=(9, 4))
    counts = sizes.value_counts().sort_index()
    ax.bar(counts.index.astype(int), counts.values, color=NAVY, width=0.7)
    for idx in counts.index:
        bar_x = int(idx)
        ax.text(bar_x, counts[idx] + 1, str(int(counts[idx])),
                ha="center", fontsize=7, color=SLATE)
    avg_lbl = T["chart_avg"].format(v=mean_size)
    if arabic:
        avg_lbl = _ar_label(avg_lbl)
    ax.axvline(mean_size, color=AMBER, linewidth=1.5, linestyle="--", label=avg_lbl)
    ax.legend(fontsize=9, framealpha=0)
    title  = _ar_label(T["chart_fam_title"]) if arabic else T["chart_fam_title"]
    xlabel = _ar_label(T["chart_fam_x"])     if arabic else T["chart_fam_x"]
    ylabel = _ar_label(T["chart_fam_y"])     if arabic else T["chart_fam_y"]
    _style_ax(ax, title, xlabel, ylabel)
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_CHART)


def _chart_remaining_months(enrich_df, T, arabic=False):
    if enrich_df.empty or "remaining_study_months" not in enrich_df.columns:
        return None
    df = enrich_df.dropna(subset=["remaining_study_months"]).copy()
    df["remaining_study_months"] = pd.to_numeric(df["remaining_study_months"], errors="coerce")
    df = df.dropna(subset=["remaining_study_months"])
    # Only show active students (> 0 months remaining)
    df = df[df["remaining_study_months"] > 0]
    if df.empty:
        return None

    band_keys  = ["chart_rem_6", "chart_rem_12", "chart_rem_24", "chart_rem_36", "chart_rem_36p"]
    band_en    = ["0–6 mo", "7–12 mo", "13–24 mo", "25–36 mo", "36+ mo"]
    bins       = [0, 6, 12, 24, 36, 9999]
    raw_labels = [T[k] for k in band_keys]
    df["band"] = pd.cut(df["remaining_study_months"], bins=bins, labels=band_en)
    counts = df["band"].value_counts().reindex(band_en, fill_value=0)

    display_labels = [_ar_label(l) if arabic else l for l in raw_labels]
    palette = [AMBER, "#F97316", TEAL, NAVY, SLATE]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    bars = ax.bar(display_labels, counts.values, color=palette, width=0.6)
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                str(int(val)), ha="center", fontsize=8, color=SLATE)
    title  = _ar_label(T["chart_rem_title"]) if arabic else T["chart_rem_title"]
    ylabel = _ar_label(T["chart_rem_y"])      if arabic else T["chart_rem_y"]
    _style_ax(ax, title, ylabel=ylabel)
    plt.xticks(rotation=15, ha="right", fontsize=9)
    fig.tight_layout(pad=1.5)
    return _fig_to_image(fig, width=W, height=H_CHART)


def _chart_study_level(enrich_df, T, arabic=False):
    if enrich_df.empty or "certificate" not in enrich_df.columns:
        return None
    counts = enrich_df["certificate"].value_counts()
    if arabic:
        labels = [_ar_label(str(l)) for l in counts.index]
    else:
        labels = list(counts.index)
    fig, ax = plt.subplots(figsize=(6, 6))
    _, _, autotexts = ax.pie(
        counts.values, labels=labels, autopct="%1.0f%%",
        colors=[NAVY, TEAL, AMBER, SLATE], startangle=90,
        wedgeprops=dict(width=0.55), pctdistance=0.78,
    )
    for t in autotexts:
        t.set_fontsize(8)
    title = _ar_label(T["chart_level_title"]) if arabic else T["chart_level_title"]
    ax.set_title(title, color=NAVY, fontsize=10, fontweight="bold")
    fig.tight_layout()
    return _fig_to_image(fig, width=12*cm, height=H_CHART)


def _chart_top_fields(enrich_df, T, arabic=False):
    if enrich_df.empty or "specialization" not in enrich_df.columns:
        return None
    top = enrich_df["specialization"].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(10, 6))
    ylabels = [_ar_label(str(l)) if arabic else str(l) for l in top.index[::-1]]
    bars = ax.barh(ylabels, top.values[::-1], color=TEAL, height=0.6)
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.3, bar.get_y() + bar.get_height()/2,
                str(int(w)), va="center", fontsize=7, color=SLATE)
    title  = _ar_label(T["chart_fields_title"]) if arabic else T["chart_fields_title"]
    xlabel = _ar_label(T["chart_fields_x"])      if arabic else T["chart_fields_x"]
    _style_ax(ax, title, xlabel)
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_WIDE)


# ══════════════════════════════════════════════════════════════════════════════
# TABLE STYLE
# ══════════════════════════════════════════════════════════════════════════════

def _hdr_style(arabic=False):
    font = "Amiri" if arabic else "Helvetica-Bold"
    body_font = "Amiri" if arabic else "Helvetica"
    align = "RIGHT" if arabic else "CENTER"
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor(NAVY)),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), font),
        ("FONTNAME",      (0, 1), (-1,-1), body_font),
        ("FONTSIZE",      (0, 0), (-1,-1), 8),
        ("GRID",          (0, 0), (-1,-1), 0.3, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS",(0, 1), (-1,-1), [colors.white, colors.HexColor(LIGHT)]),
        ("PADDING",       (0, 0), (-1,-1), 5),
        ("ALIGN",         (0, 0), (-1,-1), align),
    ])


def _p(text, style):
    """Wrap text in a Paragraph, applying arabic reshaping if needed."""
    return Paragraph(text, style)


def _ar_p(text, style):
    """Reshape Arabic text and wrap in a right-aligned Paragraph."""
    return Paragraph(_ar(text), style)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN BUILD FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def build_executive_report(
    students_df: pd.DataFrame,
    family_df: pd.DataFrame,
    enrich_df: pd.DataFrame,
    arabic: bool = False,
    exclude_overdue: bool = True,
    include_ending_soon_table: bool = True,
    include_study_level_section: bool = True,
    include_long_study_section: bool = True,
    include_large_family_section: bool = True,
) -> bytes:
    """
    Build the full executive PDF and return bytes.

    students_df                 — from fetch_full_students_df() filtered by caller
    family_df                   — from fetch_accompaniments_df() filtered to match
    enrich_df                   — from fetch_enrichment_df() filtered to match
    arabic                      — if True, produce the Arabic RTL version
    exclude_overdue             — strip students with end_date < today
    include_ending_soon_table   — show "Students Ending Within 6 Months" table
    include_study_level_section — show Study Level & Field Analysis section
    include_long_study_section  — show Long-Study Outliers (5+ years) section
    include_large_family_section— show Large Families (8+ members) section
    """
    if arabic:
        _ensure_arabic_font()

    T = AR if arabic else EN

    today = pd.Timestamp.today()

    # ── Optionally strip already-ended students ───────────────────────────────
    if exclude_overdue and not students_df.empty and "end_date" in students_df.columns:
        end_dt = pd.to_datetime(students_df["end_date"], errors="coerce")
        students_df = students_df[end_dt >= today].copy()

    # ── Recalculate remaining months dynamically ──────────────────────────────
    if not enrich_df.empty and "end_date" in enrich_df.columns:
        end_dates = pd.to_datetime(enrich_df["end_date"], errors="coerce")
        enrich_df = enrich_df.copy()
        enrich_df["remaining_study_months"] = (
            (end_dates - today).dt.days / 30.44
        ).round().astype("Int64")
        if exclude_overdue:
            enrich_df = enrich_df[enrich_df["remaining_study_months"] > 0]

    # ── Filter family to only active students ────────────────────────────────
    if not family_df.empty and not students_df.empty:
        active_ids = set(students_df["id"].tolist())
        family_df = family_df[family_df["student_id_fk"].isin(active_ids)].copy()

    buf = BytesIO()
    lm = rm = 2 * cm

    if arabic:
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=lm, rightMargin=rm,
            topMargin=2*cm, bottomMargin=2*cm,
        )
    else:
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=lm, rightMargin=rm,
            topMargin=2*cm, bottomMargin=2*cm,
        )

    styles = getSampleStyleSheet()

    if arabic:
        base_font      = "Amiri"
        base_font_bold = "Amiri"
        align          = "RIGHT"
    else:
        base_font      = "Helvetica"
        base_font_bold = "Helvetica-Bold"
        align          = "LEFT"

    _align_val = {"LEFT": 0, "RIGHT": 2, "CENTER": 1}[align]

    def S(name, font=base_font, **kw):
        return ParagraphStyle(name, parent=styles["Normal"],
                              fontName=font, alignment=_align_val, **kw)

    title_s   = S("T",  font=base_font_bold, fontSize=22, textColor=colors.HexColor(NAVY),
                  spaceAfter=4)
    sub_s     = S("Su", fontSize=11, textColor=colors.HexColor(SLATE), spaceAfter=12)
    h2_s      = S("H2", font=base_font_bold, fontSize=13, textColor=colors.HexColor(NAVY),
                  spaceBefore=14, spaceAfter=6)
    h3_s      = S("H3", font=base_font_bold, fontSize=10, textColor=colors.HexColor(TEAL),
                  spaceBefore=10, spaceAfter=4)
    body_s    = S("B",  fontSize=9, textColor=colors.HexColor(SLATE),
                  leading=14, spaceAfter=6)
    caption_s = S("C",  fontSize=8, textColor=colors.HexColor(SLATE), spaceAfter=10)

    def HR():
        return HRFlowable(width="100%", thickness=0.5,
                          color=colors.HexColor("#E2E8F0"), spaceAfter=8)

    def para(text, style):
        return _ar_p(text, style) if arabic else _p(text, style)

    story = []

    # ── Derived stats ─────────────────────────────────────────────────────────
    n_students  = len(students_df)
    n_family    = len(family_df)
    n_total     = n_students + n_family
    n_countries = students_df["country_abroad"].nunique() if not students_df.empty else 0

    all_bdays = pd.concat([
        students_df[["id","birthday","gender"]].assign(ptype="student", student_id_fk=students_df["id"]),
        family_df[["id","birthday","gender","student_id_fk"]].assign(ptype="family"),
    ], ignore_index=True)
    all_bdays["birthday"] = pd.to_datetime(all_bdays["birthday"], errors="coerce")
    all_bdays["age"] = (today - all_bdays["birthday"]).dt.days / 365.25
    n_under18   = int((all_bdays["age"] < 18).sum())
    pct_under18 = round(100 * n_under18 / n_total) if n_total else 0
    avg_family  = round(n_family / n_students, 1) if n_students else 0

    gender_counts = all_bdays["gender"].value_counts()
    pct_female = round(100 * gender_counts.get("Female", 0) / n_total) if n_total else 0
    pct_male   = round(100 * gender_counts.get("Male", 0)   / n_total) if n_total else 0

    top_country = students_df["country_abroad"].value_counts().idxmax() if not students_df.empty else "—"
    pct_top     = round(100 * (students_df["country_abroad"] == top_country).sum() / n_students) if n_students else 0

    if not enrich_df.empty and "remaining_study_months" in enrich_df.columns:
        rem = pd.to_numeric(enrich_df["remaining_study_months"], errors="coerce").dropna()
        avg_remaining    = round(rem.mean(), 1)
        pct_ending_soon  = round(100 * (rem <= 12).sum() / len(rem)) if len(rem) else 0
    else:
        avg_remaining   = "—"
        pct_ending_soon = "—"

    report_date = date.today().strftime("%B %Y") if not arabic else date.today().strftime("%Y/%m/%d")
    HDR = _hdr_style(arabic)

    # ── COVER ─────────────────────────────────────────────────────────────────
    story.append(para(T["title"], title_s))
    story.append(para(T["subtitle"], sub_s))

    cover_body = T["cover_body"].format(
        n_total=f"{n_total:,}", n_countries=n_countries,
        n_students=f"{n_students:,}", n_family=f"{n_family:,}",
        report_date=report_date,
    )
    story.append(para(cover_body, body_s))
    story.append(Spacer(1, 6))

    kpi_top    = [f"{n_total:,}", str(n_countries), f"{n_students:,}", f"{n_family:,}"]
    kpi_lbl1   = [T["kpi_total"], T["kpi_countries"], T["kpi_students"], T["kpi_family"]]
    kpi_mid    = [str(avg_family), f"{pct_under18}%",
                  f"{pct_female}% / {pct_male}%", f"{pct_top}%"]
    kpi_lbl2   = [T["kpi_avg_family"], T["kpi_under18"], T["kpi_gender"],
                  T["kpi_top_country"].format(country=top_country)]

    if arabic:
        kpi_top  = [_ar(v) for v in kpi_top]
        kpi_lbl1 = [_ar(v) for v in kpi_lbl1]
        kpi_mid  = [_ar(v) for v in kpi_mid]
        kpi_lbl2 = [_ar(v) for v in kpi_lbl2]

    kpi_data = [kpi_top, kpi_lbl1, kpi_mid, kpi_lbl2]
    kpi_table = Table(kpi_data, colWidths=[4.1*cm]*4)
    kpi_table.setStyle(TableStyle([
        ("FONTNAME",       (0,0), (-1,-1), base_font),
        ("FONTNAME",       (0,0), (-1,0),  base_font_bold),
        ("FONTSIZE",       (0,0), (-1,0),  18),
        ("TEXTCOLOR",      (0,0), (-1,0),  colors.HexColor(NAVY)),
        ("FONTSIZE",       (0,1), (-1,1),  7),
        ("TEXTCOLOR",      (0,1), (-1,1),  colors.HexColor(SLATE)),
        ("FONTNAME",       (0,2), (-1,2),  base_font_bold),
        ("FONTSIZE",       (0,2), (-1,2),  14),
        ("TEXTCOLOR",      (0,2), (-1,2),  colors.HexColor(TEAL)),
        ("FONTSIZE",       (0,3), (-1,3),  7),
        ("TEXTCOLOR",      (0,3), (-1,3),  colors.HexColor(SLATE)),
        ("ALIGN",          (0,0), (-1,-1), "CENTER"),
        ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
        ("ROWHEIGHT",      (0,0), (-1,-1), 18),
        ("BOX",            (0,0), (0,-1),  0.5, colors.HexColor("#E2E8F0")),
        ("BOX",            (1,0), (1,-1),  0.5, colors.HexColor("#E2E8F0")),
        ("BOX",            (2,0), (2,-1),  0.5, colors.HexColor("#E2E8F0")),
        ("BOX",            (3,0), (3,-1),  0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING",     (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 6),
    ]))
    story += [kpi_table, Spacer(1, 12), HR()]

    # ── GEOGRAPHIC DISTRIBUTION ───────────────────────────────────────────────
    story.append(para(T["geo_title"], h2_s))
    geo_body = T["geo_body"].format(
        n_countries=n_countries, top_country=top_country, pct_top=pct_top
    )
    story.append(para(geo_body, body_s))

    fam_with_country = family_df.copy()
    if "country_abroad" not in fam_with_country.columns:
        country_map = students_df.set_index("id")["country_abroad"].to_dict()
        fam_with_country["country_abroad"] = fam_with_country["student_id_fk"].map(country_map)

    geo_img = _chart_geo(students_df, fam_with_country, T, arabic)
    if geo_img:
        story.append(geo_img)
    story.append(Spacer(1, 4))

    combined_country = pd.concat([
        students_df[["country_abroad"]].assign(t="s"),
        fam_with_country[["country_abroad"]].assign(t="f"),
    ])
    ct = combined_country.groupby(["country_abroad","t"]).size().unstack(fill_value=0)
    ct["total"] = ct.sum(axis=1)
    ct = ct.nlargest(10, "total").reset_index()

    def _geo_cell(v):
        return _ar(str(v)) if arabic else v

    geo_hdr = [T["geo_rank"], T["geo_country"], T["geo_students"],
               T["geo_family"], T["geo_total"], T["geo_pct"]]
    if arabic:
        geo_hdr = [_ar(h) for h in geo_hdr]
    geo_rows = [geo_hdr]
    for i, row in ct.iterrows():
        pct = round(100 * row["total"] / n_total, 1) if n_total else 0
        geo_rows.append([
            _geo_cell(i+1), _geo_cell(row["country_abroad"]),
            _geo_cell(int(row.get("s",0))), _geo_cell(int(row.get("f",0))),
            _geo_cell(int(row["total"])), _geo_cell(f"{pct}%"),
        ])
    top10_total = int(ct["total"].sum())
    pct_top10   = round(100*top10_total/n_total, 1) if n_total else 0
    pct_other   = round(100*(n_total-top10_total)/n_total, 1) if n_total else 0
    geo_rows.append([_geo_cell(""), _geo_cell(T["geo_top10"]),
                     _geo_cell(""), _geo_cell(""),
                     _geo_cell(f"{top10_total:,}"),
                     _geo_cell(f"{pct_top10}%")])
    other_lbl = T["geo_other"].format(n=max(n_countries-10, 0))
    geo_rows.append([_geo_cell(""), _geo_cell(other_lbl if not arabic else _ar(other_lbl)),
                     _geo_cell(""), _geo_cell(""),
                     _geo_cell(f"{n_total-top10_total:,}"),
                     _geo_cell(f"{pct_other}%")])
    geo_t = Table(geo_rows, colWidths=[1.2*cm,4.5*cm,2.2*cm,3.5*cm,2*cm,2.9*cm])
    geo_t.setStyle(HDR)
    story += [geo_t, HR(), PageBreak()]

    # ── POPULATION COMPOSITION ────────────────────────────────────────────────
    story.append(para(T["comp_title"], h2_s))
    pct_family = round(100*n_family/n_total, 1) if n_total else 0
    comp_body = T["comp_body"].format(pct_family=pct_family, avg_family=avg_family)
    story.append(para(comp_body, body_s))
    pt_img = _chart_person_type(n_students, n_family, T, arabic)
    if pt_img:
        story.append(pt_img)

    rel_counts = family_df["relationship"].value_counts() if not family_df.empty else pd.Series()
    who_hdr = [T["comp_cat"], T["comp_count"], T["comp_pct"]]
    if arabic:
        who_hdr = [_ar(h) for h in who_hdr]

    def _wrow(label_key, count):
        lbl = _ar(T[label_key]) if arabic else T[label_key]
        pct_str = f"{round(100*count/n_total,1)}%" if n_total else "0%"
        return [lbl, _ar(f"{count:,}") if arabic else f"{count:,}",
                _ar(pct_str) if arabic else pct_str]

    who_data = [who_hdr,
                _wrow("comp_students",  n_students),
                _wrow("comp_spouses",   int(rel_counts.get("Spouse",0))),
                _wrow("comp_sons",      int(rel_counts.get("Son",0))),
                _wrow("comp_daughters", int(rel_counts.get("Daughter",0))),
                _wrow("comp_siblings",  int(rel_counts.get("Sibling",0)))]
    total_lbl = _ar(T["comp_total"]) if arabic else T["comp_total"]
    who_data.append([total_lbl,
                     _ar(f"{n_total:,}") if arabic else f"{n_total:,}",
                     _ar("100.0%") if arabic else "100.0%"])
    who_t = Table(who_data, colWidths=[8*cm, 4*cm, 4*cm])
    who_t.setStyle(HDR)
    story += [Spacer(1,6), who_t, HR(), PageBreak()]

    # ── AGE PROFILE & FAMILY SIZE ─────────────────────────────────────────────
    story.append(para(T["age_title"], h2_s))
    age_body = T["age_body"].format(n_under18=n_under18, pct_under18=pct_under18)
    story.append(para(age_body, body_s))
    age_img = _chart_age(all_bdays, T, arabic)
    if age_img:
        story.append(age_img)
        age_cap = T["age_caption"].format(n_under18=n_under18, pct_under18=pct_under18)
        story.append(para(age_cap, caption_s))
    fam_img = _chart_family_size(students_df, family_df, T, arabic)
    if fam_img:
        story.append(fam_img)
        fam_cap = T["fam_caption"].format(avg_family=avg_family)
        story.append(para(fam_cap, caption_s))
    story += [HR(), PageBreak()]

    # ── STUDY DURATION & TIME REMAINING ──────────────────────────────────────
    story.append(para(T["dur_title"], h2_s))
    dur_body = T["dur_body"].format(avg_remaining=avg_remaining, pct_ending_soon=pct_ending_soon)
    story.append(para(dur_body, body_s))

    rem_img = _chart_remaining_months(enrich_df, T, arabic)
    if rem_img:
        story.append(rem_img)

    if include_ending_soon_table and not enrich_df.empty and "remaining_study_months" in enrich_df.columns:
        story.append(para(T["dur_soon"], h3_s))
        soon = enrich_df.copy()
        soon["remaining_study_months"] = pd.to_numeric(soon["remaining_study_months"], errors="coerce")
        soon = soon[(soon["remaining_study_months"] > 0) & (soon["remaining_study_months"] <= 6)]
        soon = soon.sort_values("remaining_study_months")
        if not soon.empty:
            hdr = [T["dur_name"], T["dur_nid"], T["dur_country"],
                   T["dur_field"], T["dur_end"], T["dur_months"]]
            if arabic:
                hdr = [_ar(h) for h in hdr]
            soon_rows = [hdr]
            for _, r in soon.head(20).iterrows():
                nm  = str(r.get("full_name",""))[:30]
                nid = str(r.get("national_id",""))
                cty = str(r.get("study_country", r.get("student_country","")))
                fld = str(r.get("specialization",""))[:25]
                end = str(r.get("end_date",""))
                mo  = int(r["remaining_study_months"])
                if arabic:
                    soon_rows.append([_ar(nm), nid, _ar(cty), _ar(fld), end, str(mo)])
                else:
                    soon_rows.append([nm, nid, cty, fld, end, mo])
            soon_t = Table(soon_rows, colWidths=[4.5*cm,3*cm,2.5*cm,3.5*cm,2.5*cm,1.5*cm])
            soon_t.setStyle(HDR)
            story.append(soon_t)
            if len(soon) > 20:
                more_txt = T["dur_more"].format(n=len(soon)-20)
                story.append(para(more_txt, caption_s))
    story += [HR(), PageBreak()]

    # ── STUDY LEVEL & FIELD ───────────────────────────────────────────────────
    if include_study_level_section:
        story.append(para(T["level_title"], h2_s))

        level_img = _chart_study_level(enrich_df, T, arabic)
        if level_img:
            story.append(level_img)

        if not enrich_df.empty and "certificate" in enrich_df.columns:
            level_counts = enrich_df["certificate"].value_counts()
            lev_hdr = [T["level_col"], T["level_students"], T["level_pct"]]
            if arabic:
                lev_hdr = [_ar(h) for h in lev_hdr]
            lev_rows = [lev_hdr]
            for lvl, cnt in level_counts.items():
                lbl = _ar(str(lvl)) if arabic else str(lvl)
                lev_rows.append([lbl,
                                  _ar(f"{int(cnt):,}") if arabic else f"{int(cnt):,}",
                                  _ar(f"{round(100*cnt/len(enrich_df),1)}%") if arabic else f"{round(100*cnt/len(enrich_df),1)}%"])
            lev_t = Table(lev_rows, colWidths=[6*cm,4*cm,4*cm])
            lev_t.setStyle(HDR)
            story.append(lev_t)

        story.append(para(T["fields_title"], h3_s))
        field_img = _chart_top_fields(enrich_df, T, arabic)
        if field_img:
            story.append(field_img)

        if not enrich_df.empty and "specialization" in enrich_df.columns and "certificate" in enrich_df.columns:
            story.append(para(T["cross_title"], h3_s))
            top_fields = enrich_df["specialization"].value_counts().head(10).index
            cross = enrich_df[enrich_df["specialization"].isin(top_fields)]
            pivot = cross.groupby(["specialization","certificate"]).size().unstack(fill_value=0)
            pivot["Total"] = pivot.sum(axis=1)
            pivot = pivot.sort_values("Total", ascending=False)
            levels = [c for c in pivot.columns if c != "Total"]
            cross_hdr = ([T["cross_field"]] + list(levels) + ["Total"])
            if arabic:
                cross_hdr = [_ar(h) for h in cross_hdr]
            cross_rows = [cross_hdr]
            for field, row in pivot.iterrows():
                fld_lbl = _ar(str(field)[:28]) if arabic else str(field)[:28]
                cross_rows.append([fld_lbl] + [int(row.get(l,0)) for l in levels] + [int(row["Total"])])
            col_w = [5*cm] + [2.5*cm]*len(levels) + [2*cm]
            cross_t = Table(cross_rows, colWidths=col_w)
            cross_t.setStyle(HDR)
            story.append(cross_t)

        story += [HR(), PageBreak()]

    # ── KEY FINDINGS ──────────────────────────────────────────────────────────
    story.append(para(T["findings_title"], h2_s))

    if arabic:
        findings = [
            ("حجم البرنامج ملحوظ لكنه مركَّز.",
             f"{n_total:,} مشمولاً في {n_countries} دولة، غير أن أكبر 3 دول تضم الغالبية. "
             "ينبغي إيلاء شبكة مزودي الخدمة في تلك الدول الأولوية عند التعاقد."),
            ("أفراد الأسرة هم المحرك الرئيسي للأعداد.",
             f"يمثل أفراد الأسرة {pct_family}٪ من المجموع المؤمَّن. "
             "ينبغي أن تُبنى كل قرارات الأقساط والمزايا على مستوى الأسرة."),
            ("مجتمع غني بالأطفال.",
             f"{pct_under18}٪ من المشمولين دون سن 18. "
             "عمق التغطية الطبية للأطفال ذو أهمية استثنائية."),
            ("فوج يقترب من نهاية فترة الدراسة.",
             f"{pct_ending_soon}٪ من الطلاب لديهم 12 شهراً أو أقل. "
             "يجب الشروع الآن في إجراءات التجديد أو إنهاء المنحة."),
            ("الفجوة الجندرية مصدرها طبقة الطلاب.",
             f"الإجمالي {pct_male}٪ ذكور / {pct_female}٪ إناث، لكن أفراد الأسرة يكادون يكونون متساوين."),
            ("عدد قليل من الأسر الكبيرة يشكّل مخاطر استثنائية.",
             f"المتوسط {avg_family} معالاً لكل طالب. "
             "الأسر التي تضم 8 أفراد أو أكثر ينبغي إحالتها للمراجعة الاكتوارية."),
        ]
    else:
        findings = [
            ("Programme scale is meaningful but concentrated.",
             f"{n_total:,} covered people across {n_countries} countries, "
             "but the top 3 markets hold the majority. "
             "Provider-network strength in those markets should be a procurement priority."),
            ("Family members drive the headcount.",
             f"Family members are {pct_family}% of the insured pool. "
             "Every premium and benefit decision should be modelled at the family level."),
            ("This is a child-heavy population.",
             f"{pct_under18}% of all covered people are under 18. "
             "Paediatric coverage depth is disproportionately important."),
            ("A cohort is approaching end of study.",
             f"{pct_ending_soon}% of students have 12 months or fewer remaining. "
             "Renewal and exit processing should begin now."),
            ("Gender skew comes from the student tier.",
             f"Overall {pct_male}% male / {pct_female}% female, "
             "but family members are almost evenly split."),
            ("A small number of large families create outlier risk.",
             f"Average {avg_family} dependants per student. "
             "Households with 8+ members should be flagged for actuarial review."),
        ]

    for heading, body in findings:
        heading_txt = _ar(f"• {heading}") if arabic else f"<b>{heading}</b>"
        body_txt    = _ar(body) if arabic else body
        story.append(para(heading_txt, h3_s))
        story.append(para(body_txt, body_s))

    # ── LONG-STUDY OUTLIERS (5+ years) ───────────────────────────────────────
    if include_long_study_section:
        story += [HR(), PageBreak()]
        story.append(para(T["long_study_title"], h2_s))

        five_years_ago = today - pd.DateOffset(years=5)
        if not students_df.empty and "start_date" in students_df.columns:
            sd = pd.to_datetime(students_df["start_date"], errors="coerce")
            long_study = students_df[sd <= five_years_ago].copy()
            long_study["years_abroad"] = ((today - sd[long_study.index]).dt.days / 365.25).round(1)
            long_study = long_study.sort_values("years_abroad", ascending=False)

            if long_study.empty:
                story.append(para(T["long_study_none"], body_s))
            else:
                n_long = len(long_study)
                long_intro = T["long_study_body"].format(n_long=n_long)
                story.append(para(long_intro, body_s))

                ls_cols = ["national_id", "full_name", "country_abroad", "study_level", "start_date", "years_abroad"]
                ls_cols = [c for c in ls_cols if c in long_study.columns]
                ls_hdr_map = {
                    "national_id": T.get("long_study_col_nid", "National ID"),
                    "full_name": T.get("long_study_col_name", "Name"),
                    "country_abroad": T.get("long_study_col_country", "Country"),
                    "study_level": T.get("long_study_col_level", "Level"),
                    "start_date": T.get("long_study_col_start", "Start Date"),
                    "years_abroad": T.get("long_study_col_years", "Years Abroad"),
                }
                ls_header = [_ar(ls_hdr_map[c]) if arabic else ls_hdr_map[c] for c in ls_cols]
                ls_rows = [ls_header]
                for _, row in long_study.head(30).iterrows():
                    r = []
                    for c in ls_cols:
                        val = str(row[c]) if pd.notna(row[c]) else "—"
                        r.append(_ar(val) if arabic else val)
                    ls_rows.append(r)
                col_w = [2.5*cm, 5*cm, 3*cm, 2.5*cm, 2.5*cm, 2*cm][:len(ls_cols)]
                ls_t = Table(ls_rows, colWidths=col_w)
                ls_t.setStyle(HDR)
                story.append(ls_t)
        else:
            story.append(para(T["long_study_none"], body_s))

    # ── LARGE FAMILIES (8+ members) ───────────────────────────────────────────
    if include_large_family_section:
        story += [HR(), PageBreak()]
        story.append(para(T["large_family_title"], h2_s))

        if not family_df.empty and "student_id_fk" in family_df.columns:
            fam_counts = family_df.groupby("student_id_fk").size().reset_index(name="member_count")
            large_fam_ids = fam_counts[fam_counts["member_count"] >= 8]["student_id_fk"].tolist()

            if not large_fam_ids or students_df.empty:
                story.append(para(T["large_family_none"], body_s))
            else:
                large_students = students_df[students_df["id"].isin(large_fam_ids)].copy()
                large_students = large_students.merge(
                    fam_counts.rename(columns={"student_id_fk": "id"}), on="id", how="left"
                ).sort_values("member_count", ascending=False)

                n_large = len(large_students)
                lf_intro = T["large_family_body"].format(n_large=n_large)
                story.append(para(lf_intro, body_s))

                lf_cols = ["national_id", "full_name", "country_abroad", "member_count"]
                lf_cols = [c for c in lf_cols if c in large_students.columns]
                lf_hdr_map = {
                    "national_id": T.get("large_family_col_nid", "National ID"),
                    "full_name": T.get("large_family_col_name", "Name"),
                    "country_abroad": T.get("large_family_col_country", "Country"),
                    "member_count": T.get("large_family_col_count", "Family Members"),
                }
                lf_header = [_ar(lf_hdr_map[c]) if arabic else lf_hdr_map[c] for c in lf_cols]
                lf_rows = [lf_header]
                for _, row in large_students.iterrows():
                    r = []
                    for c in lf_cols:
                        val = str(int(row[c])) if c == "member_count" and pd.notna(row[c]) else (str(row[c]) if pd.notna(row[c]) else "—")
                        r.append(_ar(val) if arabic else val)
                    lf_rows.append(r)
                col_w = [3*cm, 6*cm, 4*cm, 3*cm][:len(lf_cols)]
                lf_t = Table(lf_rows, colWidths=col_w)
                lf_t.setStyle(HDR)
                story.append(lf_t)
        else:
            story.append(para(T["large_family_none"], body_s))

    story.append(Spacer(1, 12))
    footer_txt = T["footer"].format(report_date=date.today().isoformat())
    story.append(para(footer_txt, caption_s))

    doc.build(story)
    return buf.getvalue()
