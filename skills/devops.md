# DevOps & Platform Engineering — Scholarship Abroad Platform

> **Why this file exists:** The deployment configuration for this project is simple but has several non-obvious gotchas — particularly around secrets injection ordering, Streamlit Cloud's ephemeral filesystem, and Neon's serverless cold-start behaviour. Every operational procedure that has been learned the hard way is documented here.

---

## 1. Infrastructure Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  Streamlit Community Cloud                   │
│                  (free tier, auto-deploy)                    │
│                                                              │
│  Entry point: app/main.py                                    │
│  Python version: 3.11+ (set via packages.txt or auto)       │
│  Secrets: DATABASE_URL, credentials_yaml                     │
│  Filesystem: EPHEMERAL — reset on every redeploy             │
│  Concurrency: single-process (not multi-worker)              │
└────────────────────┬────────────────────────────────────────┘
                     │ psycopg2, sslmode=require
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Neon Serverless Postgres                     │
│                  (free tier, eu-central-1)                   │
│                                                              │
│  Endpoint: ep-cold-moon-al765gn5.c-3.eu-central-1           │
│  Database: neondb                                            │
│  Role: neondb_owner                                          │
│  Scales to zero when idle (cold start: ~1-2s)               │
└─────────────────────────────────────────────────────────────┘
                     │
                     │ Source control + CI/CD
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  GitHub (private)                            │
│                  ghadena/scholarship-abroad-platform         │
│                  Streamlit auto-deploys on push to main      │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Deployment Procedure (standard code change)

```bash
# 1. Make your changes locally
# 2. Test locally against SQLite (no DATABASE_URL needed):
streamlit run app/main.py

# 3. Commit and push
git add <changed files>
git commit -m "Description of change"
git push

# 4. Monitor Streamlit Cloud dashboard
# Go to share.streamlit.io → your app → "Manage app"
# Deployment takes ~2 minutes; watch for build errors in the log
```

**Auto-deploy:** Streamlit Cloud watches the `main` branch. Every push triggers a rebuild. There is no staging environment — main branch IS production.

**Rollback:** If a bad push breaks the app, rollback is:
```bash
git revert HEAD          # creates a new revert commit
git push                 # triggers redeploy to the reverted state
```
Or via GitHub UI: revert the merge commit.

---

## 3. Secrets Configuration

Secrets live in Streamlit Cloud → App settings → Secrets. They are in TOML format.

### Required secrets

```toml
DATABASE_URL = "postgresql://neondb_owner:<password>@ep-cold-moon-al765gn5.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require"

credentials_yaml = """
credentials:
  usernames:
    admin_username:
      email: admin@example.com
      name: Admin Name
      password: "$2b$12$<bcrypt_hash>"
      role: admin
    entry_username:
      email: entry@example.com
      name: Entry User Name
      password: "$2b$12$<bcrypt_hash>"
      role: entry
cookie:
  name: scholarship_cookie
  key: <long_random_string_32_chars_minimum>
  expiry_days: 30
"""
```

### The secrets injection ordering problem

`auth.py` MUST be imported before `database.py` on every page. The reason:

```python
# auth.py runs this at MODULE IMPORT TIME:
try:
    _db_url = st.secrets.get("DATABASE_URL")
    if _db_url and not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = _db_url
except Exception:
    pass

# database.py reads os.environ at MODULE IMPORT TIME:
DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_POSTGRES = bool(DATABASE_URL)
```

If `database.py` is ever imported before `auth.py` (e.g. someone imports `from app import database` at the top of a file before calling `login()`), `_USE_POSTGRES` will be `False` and the app will silently use SQLite with an empty local database.

**Rule:** Every page file must have this exact import order:
```python
from app.auth import login, logout, require_role   # ← FIRST
from app import database as db                      # ← SECOND (or later)
```

### Adding a new secret
1. Add it to Streamlit Cloud Secrets (TOML format)
2. Access it in code via `st.secrets["your_key"]` or `st.secrets.get("your_key")`
3. If it needs to be in `os.environ` (for libraries that read env vars), inject it in `auth.py` following the `DATABASE_URL` pattern

---

## 4. Neon Database Operations

### Accessing the Neon console
1. Go to [console.neon.tech](https://console.neon.tech)
2. Log in with the account that owns the Neon project
3. Select project → SQL Editor for direct query access

### Cold starts
Neon's free tier scales to zero after 5 minutes of inactivity. The first connection after idle triggers a cold start (~1-2 seconds). Users may experience a brief delay on the first page load after the app has been idle. This is normal and expected.

### Taking a manual backup
```bash
# Requires PostgreSQL client tools (pg_dump) installed locally
pg_dump "postgresql://neondb_owner:<password>@ep-cold-moon-al765gn5.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require" \
  --format=custom \
  --file="scholarship_backup_$(date +%Y%m%d_%H%M).dump"
```

Restore from backup:
```bash
pg_restore \
  -d "postgresql://neondb_owner:<password>@..." \
  --clean \
  scholarship_backup_20260524_1000.dump
```

**Frequency recommendation:** Take a backup before every bulk import run and after every significant data entry session. Store in Google Drive or similar.

### Checking the database from the command line
```bash
export DATABASE_URL="postgresql://neondb_owner:<password>@..."
python3 -c "
from app.database import init_db, fetch_students_df, fetch_accompaniments_df
import sys; sys.path.insert(0, '.')
init_db()
df = fetch_students_df()
print(f'Students: {len(df)}')
"
```

---

## 5. Running the Bulk Import

See `skills/data-engineer.md` §5 for the full procedure. Summary:

```bash
# Safe (SQLite, no production risk):
python3 scripts/bulk_import.py /path/to/file.xlsx

# Production (Neon):
DATABASE_URL="postgresql://..." python3 scripts/bulk_import.py /path/to/file.xlsx
```

**Before running against production:**
- Verify sheet names match exactly: `"student data"`, `"family data"`, `"more student data"`
- Take a Neon backup
- Run against SQLite first to preview counts

---

## 6. Adding New Python Dependencies

1. Add to `requirements.txt`
2. Commit and push — Streamlit Cloud re-installs dependencies on every deploy
3. For local dev: `pip install -r requirements.txt`

**Current `requirements.txt`:**
```
streamlit>=1.35
psycopg2-binary>=2.9
streamlit-authenticator>=0.4.2
pandas>=2.0
plotly>=5.18
matplotlib>=3.7
reportlab>=4.0
openpyxl>=3.1
pyyaml>=6.0
bcrypt>=4.0
pytest>=7.0
```

**Version pinning:** Currently uses `>=` (minimum version). This means a Streamlit Cloud rebuild could pick up a new major version that breaks the app. If you encounter mysterious breakage after a deploy with no code changes, a dependency may have released a breaking update. Fix: pin to exact versions (`==`) after confirming a working set.

---

## 7. Environment Parity

| Aspect | Local Dev | Production |
|--------|-----------|------------|
| Database | SQLite (`data/scholarship.db`) | Neon Postgres |
| Auth | Dev mode (no login) or local credentials.yaml | Streamlit Cloud secrets |
| File storage | Local filesystem persists | Ephemeral — wiped on redeploy |
| `_USE_POSTGRES` | `False` | `True` |
| Port | 8501 (default Streamlit) | Managed by Streamlit Cloud |

**Parity gap:** The dual-mode database layer means local dev tests SQLite behaviour, not Postgres behaviour. SQL that works in SQLite may fail in Postgres (e.g., type casting differences, `RETURNING` clause, function names like `char_length` vs `length`). The `_SCHEMA_SQLITE` replaces `char_length(` with `length(` for this reason. When writing new queries, always test against Postgres before deploying.

---

## 8. Monitoring & Health Checks

**Current state:** There is no automated monitoring. No alerts are configured.

**What to monitor manually:**
- Streamlit Cloud dashboard: shows if the app is running or crashed
- Neon console: shows compute usage, connection count, storage usage (free tier limits)
- App itself: the home page shows Total Students / Total Accompaniments — if these show 0, the DB connection is broken

**Common failure modes:**
| Symptom | Likely cause | Check |
|---------|-------------|-------|
| App shows 0 students on home page | DATABASE_URL secret missing or Neon offline | Check Streamlit secrets; check Neon console |
| Login fails for everyone | credentials_yaml secret malformed | Check Streamlit secrets YAML syntax |
| Login fails for one user | Wrong password hash in credentials_yaml | Regenerate hash; check for extra whitespace |
| App crashes with "No module named 'app'" | sys.path not set in a page file | Check top-3 lines of the broken page |
| Report PDF is blank in some sections | enrich_df is empty (no enrichment data for filter) | Normal if filters return students with no enrichment rows |
| Slow first page load | Neon cold start | Expected; normal after ~2s |
| Import script aborts early | Constraint violation without savepoints | Ensure using _pg_insert_safe() |

---

## 9. Local Development Setup (from scratch)

```bash
# Prerequisites: Python 3.11+, git

git clone https://github.com/ghadena/scholarship-abroad-platform.git
cd "scholarship-abroad-platform"

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Option A: Run in dev mode (no auth, SQLite, admin access)
streamlit run app/main.py
# → Opens at http://localhost:8501 with no login required

# Option B: Run with local auth
cp .streamlit/credentials.example.yaml .streamlit/credentials.yaml
# Edit credentials.yaml: replace placeholder hash with a real bcrypt hash
# python3 -c "import bcrypt; print(bcrypt.hashpw(b'testpass', bcrypt.gensalt()).decode())"
streamlit run app/main.py

# Option C: Run against Neon production DB locally (use with caution)
export DATABASE_URL="postgresql://neondb_owner:<password>@..."
streamlit run app/main.py

# Run tests
pytest tests/ -v
```

---

## 10. The `DEPLOYMENT.md` Problem

The existing `DEPLOYMENT.md` in the repo describes deployment to Render.com with SQLite on a persistent disk and to Streamlit Community Cloud with SQLite. Both are outdated — the project uses Neon Postgres.

**Until `DEPLOYMENT.md` is updated**, follow the procedures in this file (skills/devops.md) for all deployment operations. Do not follow the instructions in `DEPLOYMENT.md`.

---

## 11. Future: CI/CD Improvements

The current "CI/CD" is a single push-to-main triggering Streamlit Cloud auto-deploy. For a more robust setup:

**GitHub Actions workflow (recommended additions):**
```yaml
# .github/workflows/test.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
```

This would run the test suite on every push and block a failing push from deploying. Currently, broken code can reach production without any automated check.

**Nightly backup job (recommended):**
```yaml
# .github/workflows/backup.yml
on:
  schedule:
    - cron: '0 2 * * *'   # 2am UTC daily
jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - run: |
          pg_dump "${{ secrets.DATABASE_URL }}" \
            -F c -f backup_$(date +%Y%m%d).dump
      # Upload to S3/GCS/Google Drive
```
