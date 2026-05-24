# Scholarship Abroad Platform

A data-entry, dashboard, duplicate-detection, bulk-import, and reporting
platform for students sent abroad on government / institutional scholarships,
with their accompanying dependents.

## Stack

- **Streamlit** — multipage UI with role-based auth
- **SQLite** — local database, zero-setup (swap to Postgres for production)
- **streamlit-authenticator** — bcrypt-hashed credentials, cookie sessions
- **Plotly** — interactive dashboard charts
- **Matplotlib + ReportLab** — quarterly PDF reports
- **pandas + openpyxl** — CSV / Excel exports and bulk import

## Quick start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
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
   ```python
   python -c "import streamlit_authenticator as sa; print(sa.Hasher(['yourpassword']).generate())"
   ```
2. Change `cookie.key` to a long random string.

Then restart the app — the login screen will appear.

## Sharing with data-entry users

To add a new entry-role user, edit `.streamlit/credentials.yaml`:

```yaml
credentials:
  usernames:
    new_staff_member:
      email: their@email.com
      name: Their Full Name
      password: "$2b$12$BCRYPT_HASH_OF_THEIR_PASSWORD"
      role: entry   # "entry" or "admin"
```

Generate the hash on any machine that has the package installed:
```bash
python -c "import streamlit_authenticator as sa; print(sa.Hasher(['chosenpassword']).generate())"
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
│   ├── main.py              # Streamlit entry point (welcome page)
│   ├── auth.py              # Login, role checks, session helpers
│   ├── database.py          # SQLite schema + CRUD helpers
│   ├── validation.py        # Libyan NID format / gender / birthday checks
│   ├── report.py            # Quarterly PDF report builder
│   ├── duplicates.py        # Duplicate detection and auto-removal
│   ├── importer.py          # Excel/CSV bulk import logic
│   └── pages/
│       ├── 1_Data_Entry.py
│       ├── 2_Records.py
│       ├── 3_Dashboard.py
│       ├── 4_Import.py
│       ├── 5_Export_Report.py
│       └── 6_Admin.py       # admin role only
├── data/                    # gitignored — holds scholarship.db
├── tests/
│   ├── test_validation.py
│   ├── test_duplicates.py
│   └── test_importer.py
├── .streamlit/
│   └── credentials.example.yaml
├── .env.example
├── .gitignore
├── requirements.txt
├── Procfile                 # Render/Railway deployment
├── DEPLOYMENT.md            # Step-by-step deploy guide
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
| `id`                | INTEGER   | PK, auto-increment                                           |
| `national_id`       | TEXT      | UNIQUE, exactly 12 digits                                    |
| `student_id`        | TEXT      | UNIQUE                                                       |
| `full_name`         | TEXT      |                                                              |
| `birthday`          | DATE      |                                                              |
| `gender`            | TEXT      | Derived from NID digit 1 (1=Male, 2=Female)                  |
| `birthday_flag`     | INTEGER   | 1 if NID year ≠ birthday year                                |
| `duplicate_flag`    | INTEGER   | 1 if part of a soft-duplicate pair                           |
| `duplicate_reason`  | TEXT      | Which field caused the collision                             |
| `phone`, `email`    | TEXT      | Optional                                                     |
| `country_abroad`    | TEXT      |                                                              |
| `study_level`       | TEXT      | Bachelors / Masters / Doctorate / Certificate                |
| `study_field`       | TEXT      |                                                              |
| `start_date`        | DATE      |                                                              |
| `end_date`          | DATE      | CHECK: ≥ start_date                                          |
| `decision_no`       | TEXT      |                                                              |
| `created_at`        | TIMESTAMP |                                                              |
| `updated_at`        | TIMESTAMP |                                                              |

### `accompaniments`

| Column          | Type    | Notes                                              |
|-----------------|---------|----------------------------------------------------|
| `id`            | INTEGER | PK                                                 |
| `student_id_fk` | INTEGER | FK → `students.id` ON DELETE CASCADE               |
| `full_name`     | TEXT    |                                                    |
| `national_id`   | TEXT    | 12 digits                                          |
| `birthday`      | DATE    |                                                    |
| `relationship`  | TEXT    | Spouse / Son / Daughter / Sibling                  |
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
| Import             | admin, entry | Bulk-import students from Excel/CSV                           |
| Export & Report    | admin, entry | CSV / Excel / quarterly PDF                                   |
| Admin              | admin only   | Approve deletions, review duplicates, auto-remove exact dupes |

## Libyan NID rules

12 digits:
- **Digit 1** → Gender. `1` = Male, `2` = Female.
- **Digits 2–5** → 4-digit birth year.

If the year in the NID doesn't match the entered birthday's year, the record
is saved but flagged (`birthday_flag = 1`). Use the "Only flagged records"
filter on the Records page to find these.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for step-by-step instructions for
Streamlit Community Cloud and Render.com.
