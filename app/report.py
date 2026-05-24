"""
Quarterly PDF report generator.
"""

from datetime import date
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


QUARTER_MONTHS = {"Q1": (1, 3), "Q2": (4, 6), "Q3": (7, 9), "Q4": (10, 12)}


def _filter_quarter(df: pd.DataFrame, year: int, quarter: str) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["start_date"] = pd.to_datetime(df["start_date"])
    m_from, m_to = QUARTER_MONTHS[quarter]
    mask = (
        (df["start_date"].dt.year == year)
        & (df["start_date"].dt.month >= m_from)
        & (df["start_date"].dt.month <= m_to)
    )
    return df[mask]


def _chart_to_image(fig) -> Image:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=15 * cm, height=8 * cm)


def _make_charts(df: pd.DataFrame) -> list:
    images = []

    if not df.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        counts = df["country_abroad"].value_counts()
        ax.bar(counts.index, counts.values, color="#2563eb")
        ax.set_title("Students by Country")
        ax.set_ylabel("Number of Students")
        plt.xticks(rotation=45, ha="right")
        images.append(_chart_to_image(fig))

    if not df.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        counts = df["study_level"].value_counts()
        ax.pie(counts.values, labels=counts.index, autopct="%1.0f%%",
               colors=["#2563eb", "#10b981", "#f59e0b", "#ef4444"])
        ax.set_title("Study Level Distribution")
        images.append(_chart_to_image(fig))

    if not df.empty and df["gender"].notna().any():
        fig, ax = plt.subplots(figsize=(8, 4))
        counts = df["gender"].value_counts()
        ax.pie(counts.values, labels=counts.index, autopct="%1.0f%%",
               colors=["#3b82f6", "#ec4899"])
        ax.set_title("Gender Split")
        images.append(_chart_to_image(fig))

    return images


def build_quarterly_report(
    students_df: pd.DataFrame,
    accomp_df: pd.DataFrame,
    year: int,
    quarter: str,
) -> bytes:
    q_students = _filter_quarter(students_df, year, quarter)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        fontSize=20, textColor=colors.HexColor("#1e3a8a"), spaceAfter=12,
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        textColor=colors.HexColor("#1e3a8a"), spaceBefore=12, spaceAfter=8,
    )

    story = []
    story.append(Paragraph("Scholarship Abroad Programme", title_style))
    story.append(Paragraph(f"Quarterly Report — {quarter} {year}", styles["Heading2"]))
    story.append(Paragraph(f"Generated on {date.today().isoformat()}", styles["Italic"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Summary", h2))
    total_students = len(q_students)
    if total_students and not accomp_df.empty:
        q_ids = set(q_students["id"].tolist())
        q_accomp = accomp_df[accomp_df["student_id_fk"].isin(q_ids)]
    else:
        q_accomp = pd.DataFrame()
    n_countries = q_students["country_abroad"].nunique() if total_students else 0
    n_flagged = int(q_students["birthday_flag"].sum()) if total_students else 0

    kpi_data = [
        ["Metric", "Value"],
        ["Students starting this quarter", str(total_students)],
        ["Accompaniments", str(len(q_accomp))],
        ["Distinct destination countries", str(n_countries)],
        ["Records flagged for review", str(n_flagged)],
    ]
    kpi_table = Table(kpi_data, colWidths=[10 * cm, 4 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 16))

    if total_students == 0:
        story.append(Paragraph("No students started their programme in this quarter.",
                               styles["Normal"]))
        doc.build(story)
        return buf.getvalue()

    story.append(Paragraph("Visual Breakdown", h2))
    for img in _make_charts(q_students):
        story.append(img)
        story.append(Spacer(1, 8))

    story.append(PageBreak())

    story.append(Paragraph("Student Details", h2))
    cols = ["student_id", "full_name", "country_abroad", "study_level",
            "study_field", "start_date", "end_date"]
    headers = ["Student ID", "Name", "Country", "Level", "Field", "Start", "End"]
    table_data = [headers] + q_students[cols].astype(str).values.tolist()

    detail_table = Table(table_data, repeatRows=1,
                         colWidths=[2 * cm, 3.5 * cm, 2.5 * cm, 2 * cm, 2.5 * cm, 2 * cm, 2 * cm])
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(detail_table)

    doc.build(story)
    return buf.getvalue()
