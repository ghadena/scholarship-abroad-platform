# Data Analysis & Reporting — Scholarship Abroad Platform

> **Why this file exists:** The platform's primary analytical output is the Executive PDF report (`report.py`). Understanding how its KPIs are calculated, what the charts mean, and what the data actually represents is essential for anyone asked to interpret, extend, or correct the report. This document also explains what good analysis looks like for this specific dataset — including known biases and gaps.

---

## 1. The Report: What It Is and Who It's For

The Executive PDF report (`build_executive_report()` in `app/report.py`) is modelled on an Insurance Coverage Executive Report format. Its audience is programme managers and decision-makers, not data analysts. It answers the question: **"Who is in the scholarship abroad programme, where, how long, and what should we do about it?"**

The report is generated on demand from the Export & Report page. It respects the active country and gender filters — you can generate a "UK only" or "Female students only" report.

---

## 2. Data Source for Analytics

**Always use `fetch_full_students_df()`** for any analytical query. This is the students table LEFT JOIN student_enrichment with COALESCE, giving enrichment values priority over placeholder values.

**Do NOT analyse `fetch_students_df()`** for anything involving study level, field, country, or dates — it returns placeholder values for ~1,800 students whose enrichment data exists.

```python
from app.database import fetch_full_students_df, fetch_accompaniments_df, fetch_enrichment_df

students = fetch_full_students_df()   # ← use this for all analytics
family   = fetch_accompaniments_df()
enrich   = fetch_enrichment_df()
```

---

## 3. KPI Definitions

| KPI | Calculation | Source column | Notes |
|-----|-------------|---------------|-------|
| Total covered people | `len(students) + len(family)` | — | Students + all accompaniments |
| Total students | `len(students)` | `students` table | Each row = one scholarship recipient |
| Total family members | `len(family)` | `accompaniments` table | Can have 0–10+ per student |
| Countries reached | `students["country_abroad"].nunique()` | `country_abroad` (COALESCE) | Count of distinct non-null countries |
| Avg. family per student | `len(family) / len(students)` | — | Mean dependants per scholarship holder |
| % under 18 | `(age < 18).sum() / n_total * 100` | `birthday` (both tables) | Computed from DOB; see age calculation below |
| Female / Male share | `gender value_counts / n_total * 100` | `gender` | Gender is derived from NID; see caveats |
| % ending soon | `(remaining_study_months <= 12).sum() / len(enrich) * 100` | `remaining_study_months` | Only students with enrichment records |
| Avg. remaining months | `enrich["remaining_study_months"].mean()` | `remaining_study_months` | Only enriched students; excludes 14 with no record |

### Age Calculation
```python
today = pd.Timestamp.today()
df["birthday"] = pd.to_datetime(df["birthday"], errors="coerce")
df["age"] = (today - df["birthday"]).dt.days / 365.25
```

Uses 365.25 days/year to account for leap years. Computed at report generation time — age is always current as of when the PDF is produced.

### Gender Derivation Caveat
Gender is derived from NID digit 1 at insert time, not entered by users. This means:
- If the NID is wrong (birthday_flag situation), the gender may also be wrong
- Family members also have gender derived from their NID
- ~small number of records may have `gender = None` if NID digit 1 is not 1 or 2

For aggregate gender statistics, NULL genders are excluded from the denominator in the report's pie chart.

---

## 4. Chart-by-Chart Explanation

### Section 1: KPI Banner (Cover Page)
A 4-column × 4-row table. Top row = big numbers (headline stats). Second row = labels. Third row = secondary metrics. Fourth row = labels.

Not a chart — a ReportLab `Table` object. No interactivity.

### Section 2: Geographic Distribution
**Chart type:** Horizontal grouped bar chart (matplotlib `barh`)  
**What it shows:** Top 10 countries by total covered people (students + family combined)  
**Why top 10:** The distribution is heavily concentrated. Top 3 countries typically hold 60%+ of all students. Countries 11+ represent noise individually.  
**Grouped bars:** Navy = students, Teal = family members  
**Followed by:** A table showing the same data with exact counts and % of programme

**Analytical insight:** The concentration metric matters for insurance negotiation — if 60% of students are in one country, provider-network strength in that country is critical.

### Section 3: Population Composition
**Chart type:** Donut chart (matplotlib `pie` with `width=0.5`)  
**What it shows:** Students vs family members as % of total  
**Centre label:** Total covered people  
**Followed by:** A breakdown table (students, spouses, sons, daughters, siblings)

### Section 4: Age Profile & Family Size
**Chart 1:** Bar chart of age bands (0–5, 6–12, 13–17, 18–25, 26–35, 36–45, 46–55, 56–65, 66+)  
**Colour logic:** Under-18 bands (0–5, 6–12, 13–17) are highlighted in AMBER. Adult bands in NAVY.  
**Data source:** `all_bdays` — a DataFrame combining student birthdays AND family member birthdays  
**Why:** The age profile of the entire insured population matters for actuarial/insurance purposes, not just the students

**Chart 2:** Family size distribution (bar chart of "how many students have 0 family members, 1 family member, 2...") with a dashed AMBER line showing the mean.

### Section 5: Study Duration & Time Remaining
**Data source:** `enrich_df["remaining_study_months"]`  
**Chart type:** Bar chart with 6 time bands: Overdue/ended, 0–6 months, 7–12, 13–24, 25–36, 36+  
**Colour logic:** Red for overdue/ended, amber for 0–6 (urgent), orange for 7–12, then teal/navy/slate for longer remaining

**Table:** Students ending within 6 months (up to 20 rows in PDF; note says how many total)  
**Fields shown:** Name, National ID, Country, Field, End Date, Months Left

**Important limitation:** This section is only as good as `remaining_study_months` in `student_enrichment`. This value was calculated at the time the enrichment sheet was prepared (before import). It is NOT dynamically recalculated. As time passes, the "remaining months" value becomes stale. To get a current value, you need to either: (a) recalculate from `end_date - today`, or (b) get a refreshed source file from the source organisation.

**Better calculation** (to be implemented):
```python
from datetime import date
enrich_df["remaining_study_months_current"] = (
    (pd.to_datetime(enrich_df["end_date"]) - pd.Timestamp.today()).dt.days / 30.44
).clip(lower=0).round(0).astype(int)
```

### Section 6: Study Level & Field Analysis
**Chart 1:** Donut pie of certificate levels (Bachelors/Masters/Doctorate/Certificate)  
**Table:** Level breakdown with counts and percentages  
**Chart 2:** Horizontal bar chart of top 15 specialisations  
**Cross-table:** Top 10 fields × study level (pivot table)

**Limitation:** This section uses `enrich_df["certificate"]` and `enrich_df["specialization"]`, which only covers the ~1,860 students with enrichment records. The 14 students without enrichment are excluded from this section.

### Section 7: Key Findings + Recommended Next Steps
Auto-generated narrative text based on the computed statistics. Fixed wording with variable substitution. Not AI-generated — deterministic. If the numbers change, the text updates automatically.

---

## 5. Dashboard Analytics (3_Dashboard.py)

The Dashboard uses **Plotly** (interactive) unlike the report (static matplotlib). Current charts:

| Chart | What it shows | Current data source | Correct data source |
|-------|--------------|---------------------|---------------------|
| Students by Country | Bar of country counts | `fetch_students_df()` ← WRONG | `fetch_full_students_df()` |
| Study Level Distribution | Pie of study_level values | `fetch_students_df()` ← WRONG | `fetch_full_students_df()` |
| Gender Split | Pie of gender values | `fetch_students_df()` | Same (gender is in students table) |
| Students Starting per Quarter | Line of quarterly intake | `fetch_students_df()` | `fetch_full_students_df()` (start_date is enriched) |

**The fix is a one-line change on line 22 of `3_Dashboard.py`:**
```python
# Change this:
df = db.fetch_students_df()
# To this:
df = db.fetch_full_students_df()
```

---

## 6. Known Analytical Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| `remaining_study_months` is static (from import date) | Expiry analysis is stale | Recalculate from `end_date` dynamically |
| 14 students have no enrichment record | Excluded from study-level/field/duration analysis | Obtain missing data from source org |
| Gender derived from NID only | If NID is wrong, gender is wrong | Cross-check with birthday_flag records |
| No data on insurance claims or costs | Can't do actuarial analysis | Would require additional data source |
| Accompaniment country not stored | Family geographic distribution inferred from student's country | Family members are assumed to be in the same country as the student |
| No historical snapshots | Can't compare programme size over time | Would require a fact table with periodic snapshots |

### The Accompaniment Country Inference
The `_chart_geo()` function in `report.py` joins family members to student countries:
```python
if "country_abroad" not in fam_with_country.columns:
    country_map = students_df.set_index("id")["country_abroad"].to_dict()
    fam_with_country["country_abroad"] = fam_with_country["student_id_fk"].map(country_map)
```
Family members are assumed to live in the same country as their student. This is a reasonable assumption (they accompanied the student abroad) but is not verified. A family member could theoretically be in a different country.

---

## 7. Adding New Analytics

### Adding a new chart to the PDF report

1. Write a chart builder function following the `_chart_geo()` / `_chart_remaining_months()` pattern:
```python
def _chart_new_thing(df) -> Image | None:
    if df.empty:
        return None
    fig, ax = plt.subplots(figsize=(9, 4))
    # ... draw chart ...
    _style_ax(ax, "Chart Title", xlabel="X Label", ylabel="Y Label")
    fig.tight_layout()
    return _fig_to_image(fig, width=W, height=H_CHART)
```

2. Call `plt.close(fig)` inside `_fig_to_image()` (it already does this — don't add another close call)

3. Add to `build_executive_report()`:
```python
img = _chart_new_thing(enrich_df)
if img:
    story.append(img)
```

4. Add a `PageBreak()` before each major section if needed to keep layout clean

### Adding a new Dashboard chart
Plotly charts in `3_Dashboard.py`:
```python
import plotly.express as px
fig = px.bar(df.groupby("some_column").size().reset_index(name="count"),
             x="some_column", y="count", title="Chart Title")
st.plotly_chart(fig, use_container_width=True)
```

---

## 8. The `data_quality_report.xlsx` — What's In It

This file was generated during the initial data quality analysis. It contains 7 sheets:

| Sheet | Content |
|-------|---------|
| Students without enrichment | Records in students table with no matching enrichment row |
| NID-birthday mismatches | Records where birthday_flag=1 |
| Malformed family NIDs | Family NIDs that had to be padded |
| Unknown relationships | Relationship strings that fell back to "Sibling" |
| Missing student IDs | Records where student_id was set to NID as fallback |
| Placeholder study data | Records with country="Unknown", field="N/A" |
| Summary | Counts and overview |

This file was sent to the source organisation for correction. No response had been received as of 2026-05-24.
