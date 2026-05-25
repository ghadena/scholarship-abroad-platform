# Data Analysis & Reporting — Scholarship Abroad Platform

> **Why this file exists:** The platform's primary analytical output is the Executive PDF report (`report.py`). Understanding how its KPIs are calculated, what the charts mean, and what the data actually represents is essential for anyone asked to interpret, extend, or correct the report. This document also explains what good analysis looks like for this specific dataset — including known biases and gaps.

---

## 1. The Report: What It Is and Who It's For

The Executive PDF report (`build_executive_report()` in `app/report.py`) is modelled on an Insurance Coverage Executive Report format. Its audience is programme managers and decision-makers, not data analysts. It answers the question: **"Who is in the scholarship abroad programme, where, how long, and what should we do about it?"**

The report is generated on demand from the Export & Report page. It respects the active country and gender filters — you can generate a "UK only" or "Female students only" report.

**Signature:**
```python
build_executive_report(students_df, family_df, enrich_df, arabic=False, exclude_overdue=True)
```

`exclude_overdue=True` (default) strips students with `end_date < today` before all calculations. The Export page exposes a checkbox to toggle this. Pass `exclude_overdue=False` to include all students regardless of end date.

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
| % ending soon | `(remaining_study_months <= 12).sum() / len(enrich) * 100` | computed from `end_date` | Only students with enrichment records |
| Avg. remaining months | `enrich["remaining_study_months"].mean()` | computed from `end_date` | Only enriched students |

### Age Calculation
```python
today = pd.Timestamp.today()
df["birthday"] = pd.to_datetime(df["birthday"], errors="coerce")
df["age"] = (today - df["birthday"]).dt.days / 365.25
```

Uses 365.25 days/year to account for leap years. Computed at report generation time — age is always current.

### Gender Derivation Caveat
Gender is derived from NID digit 1 at insert time, not entered by users. If the NID is wrong (birthday_flag situation), the gender may also be wrong. NULL genders are excluded from the denominator in the report's pie chart.

---

## 4. `remaining_study_months` — Always Dynamic

`remaining_study_months` is **not stored** in the database. It is always calculated at runtime from `end_date - today`:

```python
enrich_df["remaining_study_months"] = (
    (pd.to_datetime(enrich_df["end_date"]) - pd.Timestamp.today()).dt.days / 30.44
).clip(lower=0).round(0).astype(int)
```

This means the value is always current as of when the report is generated. Negative values (end date in the past) are clipped to 0. The `exclude_overdue` flag strips these students before this calculation runs.

---

## 5. Chart-by-Chart Explanation

### Section 1: KPI Banner (Cover Page)
A 4-column × 4-row table. Top row = big numbers (headline stats). Second row = labels. Third row = secondary metrics. Fourth row = labels. Not a chart — a ReportLab `Table` object.

### Section 2: Geographic Distribution
**Chart type:** Horizontal grouped bar chart (`barh`)  
**What it shows:** Top 10 countries by total covered people (students + family combined)  
**Grouped bars:** Navy = students, Teal = family members  
**Followed by:** Table with exact counts and % of programme

### Section 3: Population Composition
**Chart type:** Donut chart  
**What it shows:** Students vs family members as % of total  
**Centre label:** Total covered people  
**Followed by:** Breakdown table (students, spouses, sons, daughters, siblings, unknowns)

### Section 4: Age Profile & Family Size
**Chart 1:** Bar chart of age bands (0–5, 6–12, 13–17, 18–25, 26–35, 36–45, 46–55, 56–65, 66+)  
Under-18 bands highlighted in AMBER; adult bands in NAVY.  
**Data source:** Combined student + family birthdays (full insured population)

**Chart 2:** Family size distribution — bar chart of "how many students have 0 family members, 1, 2, ..." with a dashed AMBER line showing the mean.

### Section 5: Study Duration & Time Remaining
**Data source:** `remaining_study_months` computed from `end_date - today`  
**Chart type:** Bar chart with 6 time bands: Overdue/ended, 0–6, 7–12, 13–24, 25–36, 36+  
**Colour logic:** Red for overdue/ended, amber for 0–6, orange for 7–12, then teal/navy/slate  
**Table:** Students ending within 6 months (up to 20 rows; note says total count)

### Section 6: Study Level & Field Analysis
**Chart 1:** Donut pie of certificate levels (Bachelors / Masters / Doctorate / Certificate / Specialization)  
**Table:** Level breakdown with counts and percentages  
**Chart 2:** Horizontal bar chart of top 15 specialisations  
**Cross-table:** Top 10 fields × study level (pivot table)

Data source: `enrich_df["certificate"]` and `enrich_df["specialization"]`. Students without enrichment rows are excluded from this section.

### Section 7: Long-Study Outliers (5+ years abroad)
Students whose `start_date ≤ (today - 5 years)`. Shows count and a table with name, country, study level, and years abroad (calculated as `(today - start_date).days / 365.25`). Gives programme managers visibility into students who may be overdue for review.

### Section 8: Large-Family Outliers (8+ accompanying members)
Students with 8 or more entries in the `accompaniments` table. Shows count and a table with name, country, and member count. Relevant for insurance/coverage cost analysis.

---

## 6. Dashboard Analytics (3_Dashboard.py)

The Dashboard uses **Plotly** (interactive) unlike the report (static matplotlib). Current charts:

| Chart | What it shows | Current status |
|-------|--------------|----------------|
| Students by Country | Bar of country counts | ⚠ Uses `fetch_students_df()` — shows placeholder data. Change line 22 to `fetch_full_students_df()` |
| Study Level Distribution | Pie of study_level values | ⚠ Same fix needed |
| Gender Split | Pie of gender values | OK (gender is in students table) |
| Students Starting per Quarter | Line of quarterly intake | ⚠ start_date is enriched — needs fix |

**One-line fix on line 22 of `3_Dashboard.py`:**
```python
# Change:
df = db.fetch_students_df()
# To:
df = db.fetch_full_students_df()
```

---

## 7. Known Analytical Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| Students without enrichment record | Excluded from study-level/field/duration analysis | Obtain missing data from source org |
| Gender derived from NID only | If NID is wrong, gender is wrong | Cross-check with birthday_flag records |
| No data on insurance claims or costs | Can't do actuarial analysis | Would require additional data source |
| Accompaniment country not stored | Family geographic distribution inferred from student's country | Family members are assumed to be in the same country as the student |
| No historical snapshots | Can't compare programme size over time | Would require periodic snapshot table |
| Dashboard excludes ended students | `end_date < today` records don't appear in row count | By design; use Export page with exclude_overdue=False to see all |

### The Accompaniment Country Inference
```python
if "country_abroad" not in fam_with_country.columns:
    country_map = students_df.set_index("id")["country_abroad"].to_dict()
    fam_with_country["country_abroad"] = fam_with_country["student_id_fk"].map(country_map)
```
Family members are assumed to live in the same country as their student — reasonable but unverified.

---

## 8. Adding New Analytics

### Adding a new chart to the PDF report

1. Write a chart builder function:
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

2. Add to `build_executive_report()`:
```python
img = _chart_new_thing(enrich_df)
if img:
    story.append(img)
```

3. Add translation keys to both `_T_EN` and `_T_AR` dicts if adding a section title or body text.

4. For bilingual sections, follow the `T = _T_AR if arabic else _T_EN` pattern already used.

### Adding a new Dashboard chart
```python
import plotly.express as px
fig = px.bar(df.groupby("some_column").size().reset_index(name="count"),
             x="some_column", y="count", title="Chart Title")
st.plotly_chart(fig, use_container_width=True)
```

---

## 9. The `data_quality_report.xlsx` — What's In It

Generated by `scripts/generate_data_quality_report.py`. Contains 7 sheets:

| Sheet | Content |
|-------|---------|
| Students without enrichment | Records in students table with no matching enrichment row |
| Missing / conflicted student IDs | `student_id = national_id` (missing real ID) OR `student_id LIKE '%?'` (conflict) |
| NID-birthday mismatches | Records where `birthday_flag=1` |
| Malformed family NIDs | Family NIDs that had to be zero-padded to 12 digits |
| Unknown relationships | Relationship strings that could not be mapped (stored as 'Unknown') |
| Placeholder study data | Records with `country_abroad='Unknown'` or `study_field='N/A'` |
| Summary | Counts and overview |

Send to the source organisation for correction after each bulk import run. Review Sheet 2 (conflicted student IDs) first — any `student_id LIKE '%?'` needs manual resolution before downstream processing.
