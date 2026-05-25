# Data Engineering — Scholarship Abroad Platform

> **Why this file exists:** The data engineering work in this project is non-trivial. There are two distinct import paths (CLI bulk import for historical data, web form for ongoing entry), a dual-mode database layer that abstracts Postgres from SQLite, and a COALESCE-based enrichment merge that serves as a virtual materialised view. Getting any of these wrong causes silent data loss or incorrect analytics. This document explains the patterns, the WHY behind them, and how to extend them safely.

---

## 1. The Two Import Paths — and Why They're Different

### Path A: Web Form (ongoing, one record at a time)
**Files:** `app/pages/1_Data_Entry.py` → `app/database.insert_student()`  
**Use case:** Day-to-day data entry as new scholarship decisions are issued.  
**Validation:** Full form validation via `app/validation.py` before any DB write.  
**Transaction scope:** Single student + their accompaniments in one transaction. `flag_soft_duplicates()` runs after commit.  
**NID validation:** Enforced at form level (12 digits, format check, year cross-check with birthday).

### Path B: CLI Bulk Import (historical data, batch)
**File:** `scripts/bulk_import.py`  
**Use case:** One-time or periodic bulk loads from three-sheet Excel files.  
**Validation:** Lighter — format cleaning (`clean_nid`, `clean_date`) but no full `validate_student_form()` check. Invalid rows are skipped with a console print.  
**Transaction scope:** One open connection for all inserts. Per-row SAVEPOINTs isolate failures.  
**Why separate:** The web form UI is too slow for 1,800+ records. The CLI script uses `ON CONFLICT` for conflict handling. They serve different operational modes.

> **Note:** `app/importer.py` is dead code — SQLite-only, no callers. It should be deleted.

---

## 2. The Dual-Mode Database Layer

The most important architectural decision in the data layer.

```
DATABASE_URL set in environment?
        YES                     NO
         │                      │
    psycopg2               sqlite3
    Neon Postgres         data/scholarship.db
    Production            Local dev
```

**How it works:**
```python
# database.py — evaluated ONCE at module import time
DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_POSTGRES = bool(DATABASE_URL)
```

This flag is immutable for the lifetime of the process. It cannot be changed after import. The consequence: `auth.py` MUST inject `DATABASE_URL` into `os.environ` before `database.py` is ever imported. This happens because `auth.py` is imported first on every page.

**The `_execute()` bridge:**
```python
def _execute(conn, sql: str, params=()):
    if _USE_POSTGRES:
        sql = sql.replace("?", "%s")    # Postgres uses %s, SQLite uses ?
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur
```

**Rule:** Always write SQL with `?` placeholders. Always use `_execute()` rather than `conn.cursor().execute()` directly. The only exception is within `bulk_import.py` which already uses `%s` directly because it is Postgres-only.

**The RETURNING clause difference:**
```python
# Postgres: use RETURNING id to get the new row's PK
if _USE_POSTGRES:
    cur = _execute(conn, "INSERT INTO students (...) VALUES (...) RETURNING id", vals)
    student_pk = cur.fetchone()[0]
else:
    # SQLite: use lastrowid
    cur = _execute(conn, "INSERT INTO students (...) VALUES (...)", vals)
    student_pk = cur.lastrowid
```

This pattern appears in `insert_student()` and must be replicated in any new INSERT that needs to return the new PK.

---

## 3. The Enrichment Merge (Virtual Materialised View)

### The problem it solves
The historical bulk import had incomplete data for the `students` table. Required fields like `study_level`, `study_field`, `country_abroad`, `start_date`, `end_date`, `decision_no` could not be populated from the "student data" Excel sheet alone. Placeholder values were inserted:
- `study_level = 'Bachelors'` (required by DB CHECK constraint; enrichment overrides this)
- `study_field = 'N/A'`
- `country_abroad = 'Unknown'` (or actual country from the student sheet when available)
- `start_date = '2020-01-01'`
- `end_date = '2026-01-01'`
- `decision_no = 'N/A'`

A richer "more student data" sheet contained the authoritative values. Rather than patching the `students` table in place, a separate `student_enrichment` table was created, and a COALESCE query at read time serves the merged view.

### The COALESCE logic
```sql
COALESCE(e.study_country,  s.country_abroad) AS country_abroad
COALESCE(e.certificate,    s.study_level)    AS study_level
COALESCE(e.specialization, s.study_field)    AS study_field
COALESCE(e.start_date,     s.start_date)     AS start_date
COALESCE(e.end_date,       s.end_date)       AS end_date
COALESCE(e.decision_no,    s.decision_no)    AS decision_no
```

**Semantics:** Enrichment wins when non-NULL. Student fallback activates for students with no enrichment row (LEFT JOIN produces NULL for all `e.*` columns → COALESCE falls back to `s.*`).

**Important:** `students.study_level` CHECK constraint only allows `('Bachelors', 'Masters', 'Doctorate', 'Certificate')`. "Specialization" lives only in `student_enrichment.certificate` — the COALESCE serves it correctly at read time.

### When to use which fetch function

| Situation | Function | Why |
|-----------|----------|-----|
| Reports, exports, executive PDF | `fetch_full_students_df()` | Need accurate enriched values |
| Admin duplicate review | `fetch_students_df()` | Need raw values to see what was actually entered |
| Dashboard charts | `fetch_full_students_df()` | Prevents placeholder values in charts |
| Insert/delete operations | Neither — use `get_conn()` directly | CRUD doesn't need the joined view |

### `remaining_study_months` — NOT stored

`remaining_study_months` is always calculated dynamically at runtime. It is **not** stored in the DB by `bulk_import.py` (the source Excel had a static column that went stale). Calculate wherever needed:

```python
enrich_df["remaining_study_months"] = (
    (pd.to_datetime(enrich_df["end_date"]) - pd.Timestamp.today()).dt.days / 30.44
).clip(lower=0).round(0).astype(int)
```

The `remaining_study_months` column still exists in the schema as a nullable field for any manually entered values, but bulk import does not write to it.

### Adding new enrichment fields
If the source organisation provides additional enrichment data (e.g. GPA, institution name):
1. Add column to `student_enrichment` in `_SCHEMA_PG` and `_SCHEMA_SQLITE`
2. Add to `_ensure_columns()` for migration on existing DBs
3. Add to `import_enrichment()` in `bulk_import.py`
4. Add COALESCE in `fetch_full_students_df()` if there's a corresponding students column to fall back to, otherwise `SELECT e.new_field` directly

---

## 4. Per-Row Savepoints — Why They Exist

In Postgres (unlike SQLite), a single unhandled exception inside an open transaction sets the transaction into an `aborted` state. Every subsequent statement fails with:
```
psycopg2.errors.InFailedSqlTransaction: current transaction is aborted,
commands ignored until end of transaction block
```

The bulk import processes 1,800+ rows. Source data has duplicates, malformed NIDs, constraint violations. Without savepoints, the first bad row kills the entire import.

```python
def _pg_insert_safe(conn, sql, params):
    cur = conn.cursor()
    cur.execute("SAVEPOINT sp")
    try:
        cur.execute(sql, params)
        cur.execute("RELEASE SAVEPOINT sp")
        return cur
    except Exception as e:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
        raise e  # re-raise so the caller can log and skip
```

**Pattern for any future Postgres bulk operation:** Wrap each row in a savepoint. Never let a single-row failure abort the transaction.

---

## 5. Running the Bulk Import Safely

```bash
# Step 1: Take a Neon backup
pg_dump "$DATABASE_URL" --format=custom --file="backup_$(date +%Y%m%d).dump"

# Step 2: Test against SQLite first (safe preview — no DATABASE_URL)
python3 scripts/bulk_import.py /path/to/file.xlsx

# Step 3: Run against production
DATABASE_URL="postgresql://neondb_owner:<password>@..." \
  python3 scripts/bulk_import.py /path/to/file.xlsx

# Step 4: Verify counts
DATABASE_URL="..." python3 scripts/check_db_count.py

# Step 5: Generate data quality report
DATABASE_URL="..." python3 scripts/generate_data_quality_report.py \
  --out "data_quality_report_$(date +%Y-%m-%d).xlsx"
```

**Idempotency:**
- Students: `ON CONFLICT (national_id) DO UPDATE SET duplicate_flag=1` — re-running flags existing records as duplicates rather than silently skipping. If you need a clean reimport, TRUNCATE first.
- Enrichment: `ON CONFLICT (national_id) DO UPDATE SET ...` — safe to re-run, updates existing records.
- Family (accompaniments): **NOT safe to re-run.** No UNIQUE constraint. Re-running inserts duplicate family rows. Always TRUNCATE `accompaniments` before reimport.

**For a full wipe and reimport**, first run in Neon SQL Editor:
```sql
ALTER TABLE accompaniments DROP CONSTRAINT IF EXISTS accompaniments_relationship_check;
ALTER TABLE accompaniments ADD CONSTRAINT accompaniments_relationship_check
  CHECK (relationship IN ('Spouse', 'Son', 'Daughter', 'Sibling', 'Unknown'));
TRUNCATE accompaniments, student_enrichment, students RESTART IDENTITY CASCADE;
```

**Expected column names in the Excel sheets (exact — case-sensitive in `bulk_import.py`):**

*"student data" sheet:*
`national id`, `student id`, `name`, `birthday`, `country`, `gender`

*"family data" sheet:*
`student id`, `national id`, `name`, `birthday`, `relation`, `gender`

*"more student data" sheet:*
`National_ID`, `Scholarship decision number`, `Certificate`, `Specialization`, `Study_Country_Standardized`, `Start_Date`, `End_Date`, `Duration_Months`, `Months_Already_Spent`

Note: `Remaining_Study_Months` column in the source Excel is ignored — it is calculated dynamically at runtime.

---

## 6. Duplicate and Conflict Handling

### NID duplicates (same national_id in source Excel)
Both rows get `duplicate_flag=1` and a `duplicate_reason` string explaining which row was the first occurrence. `ON CONFLICT (national_id) DO UPDATE SET duplicate_flag=1` ensures the original record is also flagged when the second import attempt hits.

### Student_id conflicts (same student_id already taken by a different NID)
The conflicting record has `?` appended to its `student_id` (e.g. `"12345?"`) and `duplicate_flag=1`. Any `student_id LIKE '%?'` needs manual review. The data quality report Sheet 2 catches these automatically.

### Soft duplicates (after web form entry)
After every web form insert, `flag_soft_duplicates(conn)` runs:
```
1. UPDATE students SET duplicate_flag=0, duplicate_reason=NULL  ← reset all
2. Self-join query to find all soft-duplicate pairs (name/NID/student_id)
3. For each pair: UPDATE both rows SET duplicate_flag=1, duplicate_reason=<field>
```

### Relationship strings in family import
- Recognised strings → mapped to canonical value (Spouse / Son / Daughter / Sibling)
- `"student"` / `"موفد"` (the student themselves) → row skipped entirely
- Any unrecognised string → `"Unknown"` (inserted with Unknown relationship)
- The `accompaniments.relationship` CHECK constraint includes `'Unknown'`

---

## 7. Schema Migration Pattern

The project uses a manual migration approach (no Alembic, no Flyway). Migrations are handled in `init_db()` + `_ensure_columns()`:

```python
def init_db():
    schema = _SCHEMA_PG if _USE_POSTGRES else _SCHEMA_SQLITE
    with get_conn() as conn:
        for stmt in schema.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        _ensure_columns(conn)   # ← adds new columns to existing tables

def _ensure_columns(conn):
    # Check if column exists; ALTER TABLE ADD COLUMN if not
```

**How to add a new column to an existing table:**
1. Add it to the CREATE TABLE statement in `_SCHEMA_PG`
2. Add a migration block in `_ensure_columns()`:

```python
for col, coltype in [("new_column", "TEXT")]:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='students' AND column_name=%s
    """, (col,))
    if not cur.fetchone():
        cur.execute(f"ALTER TABLE students ADD COLUMN {col} {coltype}")
```

`init_db()` runs on every app startup (called in `main.py`), so the migration applies automatically on the next deploy.

---

## 8. Data Lineage Map

```
Source: new_excel.xlsx (external, from source organisation)
    │
    ├─ "student data" sheet
    │       ↓  scripts/bulk_import.py → import_students()
    │   students table (with placeholder study data)
    │       ↓  app/database.fetch_full_students_df() [COALESCE join]
    │       │
    ├─ "more student data" sheet
    │       ↓  scripts/bulk_import.py → import_enrichment()
    │   student_enrichment table ──────────────────────────┘
    │                                   ↓
    │                    "canonical view" DataFrame
    │                           ↓
    │               app/report.py → PDF report
    │               app/pages/5_Export_Report.py → CSV/Excel/PDF
    │
    ├─ "family data" sheet
    │       ↓  scripts/bulk_import.py → import_family()
    │   accompaniments table
    │       ↓  app/database.fetch_accompaniments_df()
    │               ↓
    │       app/report.py (population composition, outlier sections)
    │       app/pages/5_Export_Report.py (filtered export)
    │
Ongoing:
    Web form (1_Data_Entry.py)
        ↓  app/database.insert_student()
    students + accompaniments tables
        ↓  app/duplicates.flag_soft_duplicates()
    duplicate_flag / duplicate_reason updated
```

---

## 9. Data Quality Gates

### At web form entry
- NID: must be exactly 12 numeric digits (`is_valid_nid_format()`)
- Birthday: must be present; NID year cross-check is a warning (non-blocking)
- Required fields enforced: full_name, student_id, national_id, birthday, country_abroad, study_level, study_field, start_date, end_date, decision_no
- End date ≥ start date
- Email: basic `@` presence check

### At bulk import
- Rows with missing NID, name, or birthday are skipped (logged to console)
- NIDs are cleaned (`clean_nid`) but not format-validated at input — DB CHECK enforces 12-char length
- Dates are parsed with multiple format attempts (`clean_date`)
- NID duplicates flagged with `duplicate_flag=1`; student_id conflicts get `?` suffix + flag
- Relationship strings: unrecognised → `'Unknown'`; `"student"`/`"موفد"` → skip row

### At database level
- `national_id` UNIQUE + `char_length(national_id) = 12`
- `student_id` UNIQUE
- `end_date >= start_date`
- `relationship IN ('Spouse', 'Son', 'Daughter', 'Sibling', 'Unknown')`
- `study_level IN ('Bachelors', 'Masters', 'Doctorate', 'Certificate')`

### Post-import
- Run `scripts/generate_data_quality_report.py` to get a 7-sheet Excel covering all known data quality issues
- Review Sheet 2 for any `student_id LIKE '%?'` records needing manual resolution
