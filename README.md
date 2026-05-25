# Scholarship Abroad Platform

A data-entry, dashboard, duplicate-detection, bulk-import, and reporting
platform for students sent abroad on government / institutional scholarships,
with their accompanying dependents.

## Stack

- **Streamlit** — multipage UI with role-based auth
- **Neon Postgres** — production database (serverless, free tier)
- **SQLite** — local development fallback (no setup required)
- **streamlit-authenticator** — bcrypt-hashed credentials, cookie sessions
- **Plotly** — interactive dashboard charts
- **Matplotlib + ReportLab** — executive PDF reports (bilingual AR/EN)
- **pandas + openpyxl + xlsxwriter** — Excel exports, bulk import, data quality reports

## Quick start (local dev)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run (no DATABASE_URL = SQLite fallback, dev mode, no login required)
streamlit run app/main.py
```

On first launch, if `.streamlit/credentials.yaml` is missing, the app runs in
**dev mode** — admin access with no login prompt. This is intentional for
local development. Create credentials before deploying (see below).

## First login

The app ships in **dev mode** until you create a credentials file:

```bash
cp .streamlit/credentials.example.yaml .streamlit/credentials.yaml
```

Edit `credentials.yaml`:
1. Replace `REPLACE_WITH_BCRYPT_HASH_OF_YOUR_ADMIN_PASSWORD` with a real hash:
   ```bash
   python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
   ```
2. Change `cookie.key` to a long random string.

Then restart the app — the login screen will appear.

## Connecting to production (Neon Postgres)

Set `DATABASE_URL` before starting the app:

```bash
export DATABASE_URL="postgresql://neondb_owner:<password>@<host>/neondb?sslmode=require"
streamlit run app/main.py
```

In Streamlit Cloud, this is set as a secret (see [DEPLOYMENT.md](DEPLOYMENT.md)).

## Sharing with data-entry users

To add a new user, edit `.streamlit/credentials.yaml`:

```yaml
credentials:
  usernames:
    new_staff_member:
      email: their@email.com
      name: Their Full Name
      password: "$2b$12$BCRYPT_HASH_OF_THEIR_PASSWORD"
      role: entry   # "entry" or "admin"
```

Generate the hash:
```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'chosenpassword', bcrypt.gensalt()).decode())"
```

Restart the app after editing the file.

**Entry-role users** can access: Data Entry, Records (read-only, no delete),
Import, and Export & Report.  
**Admin-role users** can also access the Admin page (deletion approvals,
duplicate review).

## File layout

```
scholarship_platform/
├── app/
│   ├── main.py              # Streamlit entry point (welcome page, calls init_db)
│   ├── auth.py              # Login, role checks, DATABASE_URL injection
│   ├── database.py          # Dual Postgres/SQLite layer; schema; CRUD helpers
│   ├── validation.py        # Libyan NID format / gender / birthday checks
│   ├── report.py            # Executive PDF report builder (bilingual AR/EN)
│   ├── duplicates.py        # Soft duplicate detection (name / NID self-join)
│   └── pages/
│       ├── 1_Data_Entry.py
│       ├── 2_Records.py
│       ├── 3_Dashboard.py
│       ├── 4_Import.py
│       ├── 5_Export_Report.py
│       └── 6_Admin.py       # admin role only
├── scripts/
│   ├── bulk_import.py                  # CLI: import 3-sheet Excel → Postgres
│   ├── generate_data_quality_report.py # Produces multi-sheet QA Excel
│   ├── find_missing_students.py        # Diff DB vs Excel; export missing rows
│   ├── import_missing_students.py      # Import missing_students_YYYY-MM-DD.xlsx
│   └── check_db_count.py              # Quick table row count check
├── skills/                  # Reference docs for Claude Code
│   ├── data-engineer.md
│   ├── data-analyst.md
│   ├── devops.md
│   ├── security.md
│   └── arabic-translation.md
├── handovers/               # Session handover notes
├── codebase-analysis/       # Auto-generated module map
├── data/                    # gitignored — local SQLite only
├── tests/
│   ├── test_validation.py
│   └── test_duplicates.py
├── .streamlit/
│   └── credentials.example.yaml
├── .gitignore               # Blocks *.xlsx, *.csv, *.pdf, *.db, *.sql, *.dump
├── requirements.txt
├── Procfile
├── DEPLOYMENT.md
└── README.md
```

## Running tests

```bash
pytest tests/ -v
```

## Database schema

### `students`

| Column              | Type      | Notes                                                        |
|---------------------|-----------|--------------------------------------------------------------|
| `id`                | INTEGER   | PK, auto-increment (SERIAL in Postgres)                      |
| `national_id`       | TEXT      | UNIQUE, exactly 12 digits                                    |
| `student_id`        | TEXT      | UNIQUE — if conflict detected on import, `?` is appended    |
| `full_name`         | TEXT      |                                                              |
| `birthday`          | DATE      |                                                              |
| `gender`            | TEXT      | Derived from NID digit 1 (1=Male, 2=Female)                  |
| `birthday_flag`     | INTEGER   | 1 if NID year ≠ birthday year                                |
| `duplicate_flag`    | INTEGER   | 1 if NID appeared more than once in source or ID conflict     |
| `duplicate_reason`  | TEXT      | Explanation of why flagged                                   |
| `phone`, `email`    | TEXT      | Optional                                                     |
| `country_abroad`    | TEXT      | Overridden by `student_enrichment.study_country` at read time|
| `study_level`       | TEXT      | Bachelors / Masters / Doctorate / Certificate (placeholder)  |
| `study_field`       | TEXT      | Overridden by `student_enrichment.specialization` at read time|
| `start_date`        | DATE      | Overridden by `student_enrichment.start_date` at read time   |
| `end_date`          | DATE      | CHECK: ≥ start_date                                          |
| `decision_no`       | TEXT      | Overridden by `student_enrichment.decision_no` at read time  |
| `created_at`        | TIMESTAMP |                                                              |

### `student_enrichment`

Authoritative values from the "more student data" sheet. Joined at read time via COALESCE.
`remaining_study_months` is NOT stored here — always recalculated as `(end_date - today) / 30.44` at runtime.

| Column                | Notes                                    |
|-----------------------|------------------------------------------|
| `national_id`         | UNIQUE, FK-like link to students         |
| `decision_no`         | Scholarship decision number              |
| `certificate`         | Bachelors / Masters / Doctorate / Certificate / Specialization |
| `specialization`      | Field of study                           |
| `study_country`       | Country (canonical value)                |
| `start_date`          |                                          |
| `end_date`            |                                          |
| `duration_months`     | Planned duration                         |
| `months_already_spent`|                                          |

### `accompaniments`

| Column          | Type    | Notes                                              |
|-----------------|---------|----------------------------------------------------|
| `id`            | INTEGER | PK                                                 |
| `student_id_fk` | INTEGER | FK → `students.id` ON DELETE CASCADE               |
| `full_name`     | TEXT    |                                                    |
| `national_id`   | TEXT    | 12 digits (zero-padded if shorter)                 |
| `birthday`      | DATE    |                                                    |
| `relationship`  | TEXT    | Spouse / Son / Daughter / Sibling / Unknown        |
| `gender`        | TEXT    | Derived from NID                                   |
| `birthday_flag` | INTEGER |                                                    |

### `deletion_requests`

| Column          | Type      | Notes                                              |
|-----------------|-----------|----------------------------------------------------|
| `id`            | INTEGER   | PK                                                 |
| `student_id_fk` | INTEGER   | FK → `students.id` ON DELETE CASCADE               |
| `requested_by`  | TEXT      | Username of the requester                          |
| `reason`        | TEXT      |                                                    |
| `status`        | TEXT      | pending / approved / rejected                      |
| `reviewed_by`   | TEXT      | Admin username                                     |
| `reviewed_at`   | TIMESTAMP |                                                    |
| `created_at`    | TIMESTAMP |                                                    |

## Features

| Page               | Roles        | What it does                                                  |
|--------------------|--------------|---------------------------------------------------------------|
| Home               | all          | Welcome + KPIs                                                |
| Data Entry         | admin, entry | Add a student + accompaniments                                |
| Records            | admin, entry | Browse, filter, request deletion; admin can delete directly   |
| Dashboard          | admin, entry | KPIs + Plotly charts + duplicate alert                        |
| Import             | admin, entry | Info page + instructions for bulk import CLI                  |
| Export & Report    | admin, entry | CSV / Excel / bilingual PDF report (AR + EN)                  |
| Admin              | admin only   | Approve deletions, review duplicates, auto-remove exact dupes |

## Bulk import

For loading historical data from a three-sheet Excel file:

```bash
DATABASE_URL="postgresql://..." \
  python3 scripts/bulk_import.py /path/to/file.xlsx
```

Expected sheet names: `"student data"`, `"family data"`, `"more student data"`.

See `skills/data-engineer.md` for full column layout and idempotency notes.

## Data quality report

```bash
DATABASE_URL="postgresql://..." \
  python3 scripts/generate_data_quality_report.py \
    --out data_quality_report_$(date +%Y-%m-%d).xlsx
```

Produces a 7-sheet Excel with: missing enrichment, NID/birthday mismatches, malformed family NIDs, unknown relationships, missing/conflicted student IDs, placeholder study data, and a summary.

## Libyan NID rules

12 digits:
- **Digit 1** → Gender. `1` = Male, `2` = Female.
- **Digits 2–5** → 4-digit birth year.

If the year in the NID doesn't match the entered birthday's year, the record
is saved but flagged (`birthday_flag = 1`). Use the "Only flagged records"
filter on the Records page to find these.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for Streamlit Community Cloud + Neon setup.
