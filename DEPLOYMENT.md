# Deployment Guide

Two free hosting options are described below. Both use SQLite. For production
with concurrent writes, migrate to Postgres (see note at the end).

---

## Option A — Streamlit Community Cloud (easiest, public URL)

**Best for:** pilots, demos, single-user or low-traffic use.  
**SQLite caveat:** the free tier has no persistent disk. The database file is
reset on every redeploy or container restart. Back up `data/scholarship.db`
regularly via the Export page, and plan to move to Postgres before going
into production.

### Steps

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   gh repo create scholarship-platform --private --source=. --push
   ```

2. **Connect to Streamlit Cloud**
   - Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
   - Click **New app** → select your repo.
   - Set **Main file path** to `app/main.py`.
   - Click **Deploy**.

3. **Set credentials via Streamlit Secrets**
   - In the app dashboard, go to **Settings → Secrets**.
   - Paste the full contents of your `credentials.yaml` under the key
     `credentials_yaml`:
     ```toml
     credentials_yaml = """
     credentials:
       usernames:
         admin_user:
           ...
     cookie:
       ...
     """
     ```
   - Update `app/auth.py` to read from `st.secrets` if the file is absent
     (the dev-mode fallback already handles missing files gracefully in
     development; for Cloud, load from `st.secrets["credentials_yaml"]`).

4. **Set DB_PATH** (optional on free tier — ephemeral anyway)
   - In Secrets: `DB_PATH = "/tmp/scholarship.db"`

### Backing up data

From the **Export & Report** page, download the Combined Excel file after
every data-entry session. Store it somewhere permanent (Google Drive, email).

### Moving to Postgres

Replace the `get_conn()` body in `app/database.py` with a `psycopg2` or
`sqlalchemy` connection. [Supabase free tier](https://supabase.com) provides
a managed Postgres instance at no cost and has a web UI for browsing data.

---

## Option B — Render.com (persistent disk, free tier)

**Best for:** persistent data without manual backups.

### Steps

1. **Push to GitHub** (same as Option A, step 1).

2. **Create a Web Service on Render**
   - Go to [render.com](https://render.com) → **New → Web Service**.
   - Connect your GitHub repo.
   - Set **Start Command** to:
     ```
     streamlit run app/main.py --server.port $PORT --server.address 0.0.0.0
     ```
     (This is also in `Procfile` — Render reads it automatically.)
   - Set **Environment** to `Python 3`.

3. **Attach a Persistent Disk**
   - In the service settings, go to **Disks → Add Disk**.
   - Mount path: `/data`
   - Size: 1 GB (free tier allows 1 GB).

4. **Set environment variables** in Render → Environment:
   ```
   DB_PATH=/data/scholarship.db
   ```
   `database.py` reads this variable automatically, so the database will
   survive restarts and redeployments.

5. **Set credentials**
   - Add an environment variable `CREDENTIALS_YAML` containing the full YAML
     text, or upload `credentials.yaml` as part of your repo (after adding it
     to `.gitignore` exceptions — not recommended).
   - The safer approach: store the YAML in a Render Secret File at path
     `.streamlit/credentials.yaml`.

6. **Deploy** — Render builds and starts the service automatically on every
   push to your main branch.

### Updating the app

```bash
git add .
git commit -m "Update"
git push
```
Render auto-deploys on push.

---

## Local development

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (First time) Set up credentials
cp .streamlit/credentials.example.yaml .streamlit/credentials.yaml
# Edit credentials.yaml — generate bcrypt hashes (see the file for instructions)

# 4. Run
streamlit run app/main.py
```

On first launch, if `.streamlit/credentials.yaml` is missing, the app runs in
**dev mode** (admin access, no login prompt) so you can explore without
setting up credentials immediately.

---

## Generating password hashes

```python
# Run once to generate hashes for credentials.yaml
import streamlit_authenticator as stauth
hashed = stauth.Hasher(["your_admin_password", "your_entry_password"]).generate()
for h in hashed:
    print(h)
```

Paste the output into `credentials.yaml`.

---

## Production checklist

- [ ] Credentials file has real bcrypt hashes (not the example placeholders)
- [ ] `credentials.yaml` is in `.gitignore`
- [ ] `DB_PATH` points to a persistent location
- [ ] Regular export backups are scheduled (or Postgres is used instead)
- [ ] `cookie.key` in `credentials.yaml` is a long random string
