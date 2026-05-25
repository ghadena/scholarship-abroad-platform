"""
Executive PDF report — matches the Insurance Coverage Executive Report format.
Sections: KPI banner · Geographic distribution · Population composition ·
          Age profile & family size · Study duration & time remaining ·
          Study level & field breakdown · Key findings.
"""

from datetime import date
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
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

W = 15 * cm
H_CHART = 7 * cm
H_WIDE  = 8 * cm


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


# ══════════════════════════════════════════════════════════════════════════════
# CHART BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def _chart_geo(students_df, family_df):
    combined = pd.concat([
        students_df[["country_abroad"]].rename(columns={"country_abroad": "country"}).assign(type="Student"),
        family_df[["country_abroad"]].rename(columns={"country_abroad": "country"}).assign(type="Family"),
    ])
    by_country = combined.groupby(["country", "type"]).size().unstack(fill_value=0)
    by_country["total"] = by_country.sum(axis=1)
    top10 = by_country.nlargest(10, "total")

    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(top10))
    h = 0.4
    s_vals = top10.get("Student", pd.Series(0, index=top10.index))
    f_vals = top10.get("Family",  pd.Series(0, index=top10.index))
    bars_s = ax.barh(y + h/2, s_vals, h, color=NAVY,  label="Students")
    bars_f = ax.barh(y - h/2, f_vals, h, color=TEAL,  label="Family members")
    for bar in list(bars_s) + list(bars_f):
        w = bar.get_width()
        if w > 0:
            ax.text(w + 20, bar.get_y() + bar.get_height()/2, f"{int(w):,}",
                    va="center", fontsize=7, color=SLATE)
    ax.set_yticks(y)
    ax.set_yticklabels(top10.index, fontsize=9)
    ax.legend(fontsize=8, framealpha=0)
    _style_ax(ax, "Top 10 Countries by Total Covered People", "Number of covered people")
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_WIDE)


def _chart_person_type(n_students, n_family):
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    # Donut — person type
    ax = axes[0]
    vals = [n_students, n_family]
    labels = ["Students", "Family Members"]
    wedges, texts, autotexts = ax.pie(
        vals, labels=None, autopct="%1.1f%%",
        colors=[NAVY, TEAL], startangle=90,
        wedgeprops=dict(width=0.5), pctdistance=0.75,
    )
    for t in autotexts:
        t.set_fontsize(9); t.set_color("white")
    ax.legend(labels, fontsize=8, loc="lower center", framealpha=0)
    ax.set_title("Person Type", color=NAVY, fontsize=10, fontweight="bold")
    ax.text(0, 0, f"{n_students+n_family:,}\nTotal", ha="center", va="center",
            fontsize=9, color=NAVY, fontweight="bold")
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_CHART)


def _chart_age(all_df):
    today = pd.Timestamp.today()
    all_df = all_df.copy()
    all_df["birthday"] = pd.to_datetime(all_df["birthday"], errors="coerce")
    all_df["age"] = (today - all_df["birthday"]).dt.days / 365.25
    bins   = [0, 6, 13, 18, 26, 36, 46, 56, 66, 200]
    labels = ["0–5", "6–12", "13–17", "18–25", "26–35", "36–45", "46–55", "56–65", "66+"]
    all_df["age_band"] = pd.cut(all_df["age"], bins=bins, labels=labels, right=False)
    counts = all_df["age_band"].value_counts().reindex(labels, fill_value=0)
    minor  = all_df["age"] < 18

    fig, ax = plt.subplots(figsize=(9, 4))
    bar_colors = [AMBER if lbl in ("0–5","6–12","13–17") else NAVY for lbl in labels]
    bars = ax.bar(labels, counts.values, color=bar_colors, width=0.7)
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 10,
                f"{int(val):,}", ha="center", fontsize=7, color=SLATE)
    legend_els = [mpatches.Patch(color=AMBER, label="Under 18 (minors)"),
                  mpatches.Patch(color=NAVY,  label="18 and above")]
    ax.legend(handles=legend_els, fontsize=8, framealpha=0)
    _style_ax(ax, "Age Distribution — Children Under 18 Highlighted", ylabel="People")
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_CHART)


def _chart_family_size(students_df, family_df):
    sizes = family_df.groupby("student_id_fk").size()
    students_no_family = set(students_df["id"]) - set(sizes.index)
    sizes = pd.concat([sizes, pd.Series(0, index=list(students_no_family))])
    mean_size = sizes.mean()

    fig, ax = plt.subplots(figsize=(9, 4))
    counts = sizes.value_counts().sort_index()
    bars = ax.bar(counts.index.astype(int), counts.values, color=NAVY, width=0.7)
    peak = counts.idxmax()
    for bar, idx in zip(bars, counts.index):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                str(int(counts[idx])), ha="center", fontsize=7, color=SLATE)
    ax.axvline(mean_size, color=AMBER, linewidth=1.5, linestyle="--",
               label=f"Avg: {mean_size:.2f}")
    ax.legend(fontsize=9, framealpha=0)
    _style_ax(ax, "Family Size per Student — Distribution",
              xlabel="Family members per student", ylabel="Number of students")
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_CHART)


def _chart_remaining_months(enrich_df):
    if enrich_df.empty or "remaining_study_months" not in enrich_df.columns:
        return None
    df = enrich_df.dropna(subset=["remaining_study_months"]).copy()
    df["remaining_study_months"] = pd.to_numeric(df["remaining_study_months"], errors="coerce")
    df = df.dropna(subset=["remaining_study_months"])
    bins   = [-999, 0, 6, 12, 24, 36, 9999]
    labels = ["Overdue / ended", "0–6 months", "7–12 months", "13–24 months", "25–36 months", "36+ months"]
    df["band"] = pd.cut(df["remaining_study_months"], bins=bins, labels=labels)
    counts = df["band"].value_counts().reindex(labels, fill_value=0)
    palette = ["#EF4444", AMBER, "#F97316", TEAL, NAVY, SLATE]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(labels, counts.values, color=palette, width=0.7)
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                str(int(val)), ha="center", fontsize=8, color=SLATE)
    _style_ax(ax, "Remaining Study Duration Distribution", ylabel="Students")
    plt.xticks(rotation=20, ha="right", fontsize=8)
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_CHART)


def _chart_study_level(enrich_df):
    if enrich_df.empty:
        return None
    counts = enrich_df["certificate"].value_counts()
    fig, ax = plt.subplots(figsize=(6, 4))
    wedges, texts, autotexts = ax.pie(
        counts.values, labels=counts.index, autopct="%1.0f%%",
        colors=[NAVY, TEAL, AMBER, SLATE], startangle=90,
        wedgeprops=dict(width=0.55), pctdistance=0.78,
    )
    for t in autotexts:
        t.set_fontsize(8)
    ax.set_title("Study Level Distribution", color=NAVY, fontsize=10, fontweight="bold")
    fig.tight_layout()
    return _fig_to_image(fig, width=12*cm, height=H_CHART)


def _chart_top_fields(enrich_df):
    if enrich_df.empty or "specialization" not in enrich_df.columns:
        return None
    top = enrich_df["specialization"].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(top.index[::-1], top.values[::-1], color=TEAL, height=0.6)
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.3, bar.get_y() + bar.get_height()/2,
                str(int(w)), va="center", fontsize=7, color=SLATE)
    _style_ax(ax, "Top 15 Study Fields", xlabel="Students")
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_WIDE)


# ══════════════════════════════════════════════════════════════════════════════
# TABLE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

_HDR = TableStyle([
    ("BACKGROUND",  (0,0), (-1,0), colors.HexColor(NAVY)),
    ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
    ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
    ("FONTSIZE",    (0,0), (-1,-1), 8),
    ("GRID",        (0,0), (-1,-1), 0.3, colors.HexColor("#D1D5DB")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor(LIGHT)]),
    ("PADDING",     (0,0), (-1,-1), 5),
    ("ALIGN",       (1,0), (-1,-1), "CENTER"),
])


# ══════════════════════════════════════════════════════════════════════════════
# MAIN BUILD FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def build_executive_report(
    students_df: pd.DataFrame,
    family_df: pd.DataFrame,
    enrich_df: pd.DataFrame,
) -> bytes:
    """
    Build the full executive PDF report and return bytes.

    students_df  — from fetch_full_students_df() (includes enrichment via COALESCE)
    family_df    — from fetch_accompaniments_df()
    enrich_df    — from fetch_enrichment_df()
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    S = lambda name, **kw: ParagraphStyle(name, parent=styles["Normal"], **kw)
    title_s  = S("T",  fontSize=22, textColor=colors.HexColor(NAVY),
                 fontName="Helvetica-Bold", spaceAfter=4)
    sub_s    = S("Su", fontSize=11, textColor=colors.HexColor(SLATE), spaceAfter=12)
    h2_s     = S("H2", fontSize=13, textColor=colors.HexColor(NAVY),
                 fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6)
    h3_s     = S("H3", fontSize=10, textColor=colors.HexColor(TEAL),
                 fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)
    body_s   = S("B",  fontSize=9,  textColor=colors.HexColor(SLATE),
                 leading=14, spaceAfter=6)
    caption_s= S("C",  fontSize=8,  textColor=colors.HexColor(SLATE),
                 fontName="Helvetica-Oblique", spaceAfter=10)

    def HR():
        return HRFlowable(width="100%", thickness=0.5,
                          color=colors.HexColor("#E2E8F0"), spaceAfter=8)

    story = []

    # ── Derived stats ─────────────────────────────────────────────────────────
    today = pd.Timestamp.today()

    # Recalculate remaining months dynamically from end_date so the stored
    # import-time value (which is now stale) is never used.
    if not enrich_df.empty and "end_date" in enrich_df.columns:
        end_dates = pd.to_datetime(enrich_df["end_date"], errors="coerce")
        enrich_df = enrich_df.copy()
        enrich_df["remaining_study_months"] = (
            (end_dates - today).dt.days / 30.44
        ).round().astype("Int64")

    n_students = len(students_df)
    n_family   = len(family_df)
    n_total    = n_students + n_family

    n_countries = students_df["country_abroad"].nunique() if not students_df.empty else 0

    # Age across everyone
    all_bdays = pd.concat([
        students_df[["id","birthday","gender"]].assign(ptype="student", student_id_fk=students_df["id"]),
        family_df[["id","birthday","gender","student_id_fk"]].assign(ptype="family"),
    ], ignore_index=True)
    all_bdays["birthday"] = pd.to_datetime(all_bdays["birthday"], errors="coerce")
    all_bdays["age"] = (today - all_bdays["birthday"]).dt.days / 365.25
    n_under18 = int((all_bdays["age"] < 18).sum())
    pct_under18 = round(100 * n_under18 / n_total) if n_total else 0
    avg_family = round(n_family / n_students, 1) if n_students else 0

    gender_counts = all_bdays["gender"].value_counts()
    pct_female = round(100 * gender_counts.get("Female", 0) / n_total) if n_total else 0
    pct_male   = round(100 * gender_counts.get("Male", 0)   / n_total) if n_total else 0

    top_country = students_df["country_abroad"].value_counts().idxmax() if not students_df.empty else "—"
    pct_top = round(100 * (students_df["country_abroad"] == top_country).sum() / n_students) if n_students else 0

    # Remaining months
    if not enrich_df.empty and "remaining_study_months" in enrich_df.columns:
        rem = pd.to_numeric(enrich_df["remaining_study_months"], errors="coerce").dropna()
        avg_remaining = round(rem.mean(), 1)
        pct_ending_soon = round(100 * (rem <= 12).sum() / len(rem)) if len(rem) else 0
    else:
        avg_remaining = "—"
        pct_ending_soon = "—"

    # ── COVER ─────────────────────────────────────────────────────────────────
    story.append(Paragraph("Scholarship Abroad Programme", title_s))
    story.append(Paragraph("Executive Report for Decision Makers", sub_s))
    story.append(Paragraph(
        f"This report presents an at-a-glance view of the insured population across the programme: "
        f"<b>{n_total:,} covered people</b> spanning <b>{n_countries} countries</b>, made up of "
        f"<b>{n_students:,} students</b> and <b>{n_family:,} family members</b>. "
        f"Generated on {date.today().strftime('%B %Y')}.",
        body_s,
    ))
    story.append(Spacer(1, 6))

    # KPI banner table
    kpi_data = [
        [f"{n_total:,}", str(n_countries), f"{n_students:,}", f"{n_family:,}"],
        ["Total covered people", "Countries reached", "Students", "Family members"],
        [f"{avg_family}", f"{pct_under18}%", f"{pct_female}% / {pct_male}%", f"{pct_top}%"],
        ["Avg. family / student", "Population under 18", "Female / Male share", f"Concentrated in {top_country}"],
    ]
    kpi_col_w = [4.1*cm] * 4
    kpi_table = Table(kpi_data, colWidths=kpi_col_w)
    kpi_table.setStyle(TableStyle([
        ("FONTNAME",  (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME",  (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",  (0,0), (-1,0),  18),
        ("TEXTCOLOR", (0,0), (-1,0),  colors.HexColor(NAVY)),
        ("FONTSIZE",  (0,1), (-1,1),  7),
        ("TEXTCOLOR", (0,1), (-1,1),  colors.HexColor(SLATE)),
        ("FONTNAME",  (0,2), (-1,2),  "Helvetica-Bold"),
        ("FONTSIZE",  (0,2), (-1,2),  14),
        ("TEXTCOLOR", (0,2), (-1,2),  colors.HexColor(TEAL)),
        ("FONTSIZE",  (0,3), (-1,3),  7),
        ("TEXTCOLOR", (0,3), (-1,3),  colors.HexColor(SLATE)),
        ("ALIGN",     (0,0), (-1,-1), "CENTER"),
        ("VALIGN",    (0,0), (-1,-1), "MIDDLE"),
        ("ROWHEIGHT", (0,0), (-1,-1), 18),
        ("BOX",       (0,0), (0,-1),  0.5, colors.HexColor("#E2E8F0")),
        ("BOX",       (1,0), (1,-1),  0.5, colors.HexColor("#E2E8F0")),
        ("BOX",       (2,0), (2,-1),  0.5, colors.HexColor("#E2E8F0")),
        ("BOX",       (3,0), (3,-1),  0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING",(0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
    ]))
    story += [kpi_table, Spacer(1, 12), HR()]

    # ── GEOGRAPHIC DISTRIBUTION ───────────────────────────────────────────────
    story.append(Paragraph("Geographic Distribution", h2_s))
    story.append(Paragraph(
        f"The programme covers {n_countries} countries, but distribution is highly skewed. "
        f"The top three markets together represent the majority of all covered people. "
        f"{top_country} alone accounts for {pct_top}% of students.",
        body_s,
    ))

    # Family df needs country — join via student
    fam_with_country = family_df.copy()
    if "country_abroad" not in fam_with_country.columns:
        country_map = students_df.set_index("id")["country_abroad"].to_dict()
        fam_with_country["country_abroad"] = fam_with_country["student_id_fk"].map(country_map)

    story.append(_chart_geo(students_df, fam_with_country))
    story.append(Spacer(1, 4))

    # Top 10 table
    combined_country = pd.concat([
        students_df[["country_abroad"]].assign(t="s"),
        fam_with_country[["country_abroad"]].assign(t="f"),
    ])
    ct = combined_country.groupby(["country_abroad","t"]).size().unstack(fill_value=0)
    ct["total"] = ct.sum(axis=1)
    ct = ct.nlargest(10, "total").reset_index()
    geo_rows = [["Rank", "Country", "Students", "Family Members", "Total", "% of programme"]]
    for i, row in ct.iterrows():
        pct = round(100 * row["total"] / n_total, 1) if n_total else 0
        geo_rows.append([
            i+1, row["country_abroad"],
            int(row.get("s", 0)), int(row.get("f", 0)),
            int(row["total"]), f"{pct}%",
        ])
    top10_total = int(ct["total"].sum())
    geo_rows.append(["", "Top 10 subtotal", "", "", f"{top10_total:,}",
                     f"{round(100*top10_total/n_total,1)}%"])
    geo_rows.append(["", f"Other {n_countries-10} countries", "", "",
                     f"{n_total-top10_total:,}",
                     f"{round(100*(n_total-top10_total)/n_total,1)}%"])

    geo_t = Table(geo_rows, colWidths=[1.2*cm, 4.5*cm, 2.2*cm, 3.5*cm, 2*cm, 2.9*cm])
    geo_t.setStyle(_HDR)
    story += [geo_t, HR(), PageBreak()]

    # ── POPULATION COMPOSITION ────────────────────────────────────────────────
    story.append(Paragraph("Population Composition", h2_s))
    story.append(Paragraph(
        f"Family members account for <b>{round(100*n_family/n_total, 1)}%</b> of all insured people. "
        f"Each student brings on average <b>{avg_family} family members</b> onto the policy.",
        body_s,
    ))
    story.append(_chart_person_type(n_students, n_family))

    # Who is covered table
    rel_counts = family_df["relationship"].value_counts() if not family_df.empty else pd.Series()
    who_data = [["Category", "Count", "% of total"]]
    for cat, col in [("Students", n_students),
                     ("Spouses",  int(rel_counts.get("Spouse", 0))),
                     ("Sons",     int(rel_counts.get("Son", 0))),
                     ("Daughters",int(rel_counts.get("Daughter", 0))),
                     ("Siblings", int(rel_counts.get("Sibling", 0)))]:
        who_data.append([cat, f"{col:,}", f"{round(100*col/n_total,1)}%"])
    who_data.append(["Total covered people", f"{n_total:,}", "100.0%"])
    who_t = Table(who_data, colWidths=[8*cm, 4*cm, 4*cm])
    who_t.setStyle(_HDR)
    story += [Spacer(1,6), who_t, HR(), PageBreak()]

    # ── AGE PROFILE & FAMILY SIZE ─────────────────────────────────────────────
    story.append(Paragraph("Age Profile & Family Size", h2_s))
    story.append(Paragraph(
        f"<b>{n_under18:,} people ({pct_under18}%)</b> of the insured population are under 18. "
        "The 6–12 band is typically the largest age cohort, followed by 36–45 year-olds.",
        body_s,
    ))
    story.append(_chart_age(all_bdays))
    story.append(caption_s and Paragraph(
        f"Figure: Age distribution. {n_under18:,} people ({pct_under18}%) are under 18.",
        caption_s,
    ))
    story.append(_chart_family_size(students_df, family_df))
    story.append(Paragraph(
        f"Figure: Family size distribution. Mean = {avg_family} dependants per student.",
        caption_s,
    ))
    story.append(HR())
    story.append(PageBreak())

    # ── STUDY DURATION & TIME REMAINING ──────────────────────────────────────
    story.append(Paragraph("Study Duration & Time Remaining", h2_s))
    story.append(Paragraph(
        f"Of students with scholarship records, the average remaining study period is "
        f"<b>{avg_remaining} months</b>. "
        f"<b>{pct_ending_soon}%</b> of students have 12 months or fewer remaining — "
        "these cases should be prioritised for renewal or exit processing.",
        body_s,
    ))
    rem_img = _chart_remaining_months(enrich_df)
    if rem_img:
        story.append(rem_img)

    # Ending-soon table
    if not enrich_df.empty and "remaining_study_months" in enrich_df.columns:
        story.append(Paragraph("Students Ending Within 6 Months", h3_s))
        soon = enrich_df.copy()
        soon["remaining_study_months"] = pd.to_numeric(soon["remaining_study_months"], errors="coerce")
        soon = soon[soon["remaining_study_months"] <= 6].sort_values("remaining_study_months")
        if not soon.empty:
            soon_rows = [["Name", "National ID", "Country", "Field", "End Date", "Months Left"]]
            for _, r in soon.head(20).iterrows():
                soon_rows.append([
                    str(r.get("full_name",""))[:30],
                    str(r.get("national_id","")),
                    str(r.get("study_country", r.get("student_country",""))),
                    str(r.get("specialization",""))[:25],
                    str(r.get("end_date","")),
                    int(r["remaining_study_months"]),
                ])
            soon_t = Table(soon_rows, colWidths=[4.5*cm,3*cm,2.5*cm,3.5*cm,2.5*cm,1.5*cm])
            soon_t.setStyle(_HDR)
            story.append(soon_t)
            if len(soon) > 20:
                story.append(Paragraph(f"… and {len(soon)-20} more (see full export).", caption_s))
    story += [HR(), PageBreak()]

    # ── STUDY LEVEL & FIELD ───────────────────────────────────────────────────
    story.append(Paragraph("Study Level & Field Analysis", h2_s))

    level_img = _chart_study_level(enrich_df)
    if level_img:
        story.append(level_img)

    # Level breakdown table
    if not enrich_df.empty and "certificate" in enrich_df.columns:
        level_counts = enrich_df["certificate"].value_counts()
        lev_rows = [["Study Level", "Students", "% of total"]]
        for lvl, cnt in level_counts.items():
            lev_rows.append([lvl, f"{int(cnt):,}", f"{round(100*cnt/len(enrich_df),1)}%"])
        lev_t = Table(lev_rows, colWidths=[6*cm, 4*cm, 4*cm])
        lev_t.setStyle(_HDR)
        story.append(lev_t)

    story.append(Paragraph("Top Study Fields", h3_s))
    field_img = _chart_top_fields(enrich_df)
    if field_img:
        story.append(field_img)

    # Field + level cross-table (top 10 fields × level)
    if not enrich_df.empty:
        story.append(Paragraph("Field × Study Level Breakdown (Top 10 Fields)", h3_s))
        top_fields = enrich_df["specialization"].value_counts().head(10).index
        cross = enrich_df[enrich_df["specialization"].isin(top_fields)]
        pivot = cross.groupby(["specialization","certificate"]).size().unstack(fill_value=0)
        pivot["Total"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("Total", ascending=False)
        levels = [c for c in pivot.columns if c != "Total"]
        cross_rows = [["Field"] + levels + ["Total"]]
        for field, row in pivot.iterrows():
            cross_rows.append([str(field)[:28]] + [int(row.get(l,0)) for l in levels] + [int(row["Total"])])
        col_w = [5*cm] + [2.5*cm]*len(levels) + [2*cm]
        cross_t = Table(cross_rows, colWidths=col_w)
        cross_t.setStyle(_HDR)
        story.append(cross_t)

    story += [HR(), PageBreak()]

    # ── KEY FINDINGS ──────────────────────────────────────────────────────────
    story.append(Paragraph("Key Findings", h2_s))

    findings = [
        ("Programme scale is meaningful but concentrated.",
         f"{n_total:,} covered people across {n_countries} countries, "
         f"but the top 3 markets hold the majority. "
         "Provider-network strength in those markets should be a procurement priority."),
        ("Family members drive the headcount, not students.",
         f"Family members are {round(100*n_family/n_total,1)}% of the insured pool. "
         "Every premium and benefit decision should be modelled at the family level."),
        ("This is a child-heavy population.",
         f"{pct_under18}% of all covered people are under 18. "
         "Paediatric coverage depth is disproportionately important."),
        ("A cohort is approaching end of study.",
         f"{pct_ending_soon}% of students have 12 months or fewer remaining. "
         "Renewal, exit processing and insurance termination planning should begin now."),
        ("Gender skew comes from the student tier.",
         f"Overall {pct_male}% male / {pct_female}% female, but family members are almost evenly split."),
        ("A small number of large families create outlier risk.",
         f"Average {avg_family} dependants per student. "
         "Households with 8+ members should be flagged for actuarial review."),
    ]
    for heading, body in findings:
        story.append(Paragraph(f"<b>{heading}</b>", h3_s))
        story.append(Paragraph(body, body_s))

    story.append(HR())
    story.append(Paragraph("Recommended Next Steps", h2_s))
    steps = [
        f"Negotiate provider-network strength in the top 3 countries — they carry the majority of the population.",
        f"Model premiums at the family level rather than per-student, given the {avg_family}× multiplier.",
        f"Strengthen paediatric benefits (preventive care, dental, vaccinations) in line with the {pct_under18}% under-18 share.",
        f"Initiate renewal/exit processing for the {pct_ending_soon}% of students with ≤12 months remaining.",
        "Flag and stress-test households with 8+ members for claim-cost concentration risk.",
        "Close remaining gender/age data gaps before next renewal to enable cleaner actuarial modelling.",
    ]
    for step in steps:
        story.append(Paragraph(f"• {step}", body_s))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"Source: Scholarship Abroad Platform database. "
        f"All figures reflect the insured population as at {date.today().isoformat()}.",
        caption_s,
    ))

    doc.build(story)
    return buf.getvalue()


