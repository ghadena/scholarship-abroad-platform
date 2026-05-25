# Deployment Guide

The platform runs on **Streamlit Community Cloud** (free tier) connected to
**Neon Serverless Postgres** (free tier). This is the current production setup.

---

## Production architecture

```
Streamlit Community Cloud  ──psycopg2──▶  Neon Postgres (eu-central-1)
       ↑
   GitHub push to main (auto-deploy)
```

- **No persistent local filesystem** — Streamlit Cloud wipes the container on every redeploy. All data lives in Neon.
- **Cold starts** — Neon's free tier scales to zero after 5 minutes idle. First request after idle takes ~1–2s. This is normal.

---

## Initial setup (one time)

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create scholarship-abroad-platform --private --source=. --push
```

### 2. Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Click **New app** → select your repo.
3. Set **Main file path** to `app/main.py`.
4. Click **Deploy**.

### 3. Set Streamlit secrets

In the app dashboard → **Settings → Secrets**, paste:

```toml
DATABASE_URL = "postgresql://neondb_owner:<password>@<host>/neondb?sslmode=require"

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

Generate password hashes:
```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

---

## Deploying a code change

```bash
# Make changes locally, test against SQLite:
streamlit run app/main.py

# Commit and push — Streamlit Cloud auto-deploys within ~2 minutes:
git add <changed files>
git commit -m "Description of change"
git push
```

**main branch IS production.** There is no staging environment. Test locally first.

**Rollback:**
```bash
git revert HEAD    # creates a new revert commit
git push           # triggers redeploy to reverted state
```

---

## Neon database operations

### Access the SQL editor

Go to [console.neon.tech](https://console.neon.tech) → your project → SQL Editor.

### Manual backup

```bash
pg_dump "postgresql://neondb_owner:<password>@<host>/neondb?sslmode=require" \
  --format=custom \
  --file="scholarship_backup_$(date +%Y%m%d_%H%M).dump"
```

**Take a backup before every bulk import.**

### Restore from backup

```bash
pg_restore \
  -d "postgresql://neondb_owner:<password>@<host>/neondb?sslmode=require" \
  --clean \
  scholarship_backup_YYYYMMDD_HHMM.dump
```

### Wipe and reimport from scratch

Run in the Neon SQL Editor first (updates the relationship constraint):

```sql
ALTER TABLE accompaniments
  DROP CONSTRAINT IF EXISTS accompaniments_relationship_check;

ALTER TABLE accompaniments
  ADD CONSTRAINT accompaniments_relationship_check
  CHECK (relationship IN ('Spouse', 'Son', 'Daughter', 'Sibling', 'Unknown'));

TRUNCATE accompaniments, student_enrichment, students RESTART IDENTITY CASCADE;
```

Then run the import locally against production:

```bash
DATABASE_URL="postgresql://..." \
  python3 scripts/bulk_import.py /path/to/new_excel.xlsx
```

---

## Bulk import procedure

```bash
# 1. Take a Neon backup (see above)

# 2. Test locally first against SQLite (safe — no DATABASE_URL):
python3 scripts/bulk_import.py /path/to/file.xlsx

# 3. Run against production:
DATABASE_URL="postgresql://..." python3 scripts/bulk_import.py /path/to/file.xlsx

# 4. Verify row counts:
DATABASE_URL="..." python3 scripts/check_db_count.py

# 5. Generate data quality report:
DATABASE_URL="..." python3 scripts/generate_data_quality_report.py \
  --out "data_quality_report_$(date +%Y-%m-%d).xlsx"
```

Expected sheet names in the Excel: `"student data"`, `"family data"`, `"more student data"`.

---

## Adding a new user

Edit `.streamlit/credentials.yaml` (local) or the `credentials_yaml` secret
(Streamlit Cloud) — add an entry under `credentials.usernames`:

```yaml
new_user:
  email: their@email.com
  name: Their Full Name
  password: "$2b$12$<hash>"
  role: entry   # or admin
```

Generate the hash:
```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'theirpassword', bcrypt.gensalt()).decode())"
```

Restart the app (or redeploy) after changing secrets.

---

## Adding a new Python dependency

1. Add to `requirements.txt`
2. Commit and push — Streamlit Cloud reinstalls on every deploy

---

## Local development setup

```bash
git clone https://github.com/ghadena/scholarship-abroad-platform.git
cd "scholarship-abroad-platform"

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Dev mode (no auth, SQLite, admin access):
streamlit run app/main.py

# With local auth:
cp .streamlit/credentials.example.yaml .streamlit/credentials.yaml
# Edit credentials.yaml — replace placeholder hashes
streamlit run app/main.py

# Against production Neon DB (use with caution — live data):
export DATABASE_URL="postgresql://..."
streamlit run app/main.py

# Run tests:
pytest tests/ -v
```

---

## Production checklist

- [ ] `DATABASE_URL` is set as a Streamlit secret (never committed to git)
- [ ] `credentials_yaml` secret has real bcrypt hashes (not example placeholders)
- [ ] `cookie.key` is a long random string (32+ chars)
- [ ] `.gitignore` blocks `*.xlsx`, `*.csv`, `*.pdf`, `*.db`, `*.sql`, `*.dump`
- [ ] Manual Neon backup taken before every bulk import
- [ ] `student_id LIKE '%?'` records reviewed after each import (see data quality report Sheet 2)
