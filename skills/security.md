# Security Engineering — Scholarship Abroad Platform

> **Why this file exists:** This platform handles personal data (names, national IDs, birthdays, phone numbers, email addresses) for ~1,800+ individuals. It also controls access to a Neon Postgres database with credentials stored in Streamlit Cloud secrets. Security failures here are not hypothetical — an exposed NID + birthday is enough to impersonate someone. This document records every security decision, its reasoning, and its current gaps.

---

## 1. Authentication Architecture

### What is used
`streamlit-authenticator` version 0.4.x, wrapping bcrypt password verification and a signed cookie-based session.

### How it works (step by step)
```
1. User loads app → Streamlit runs app/main.py
2. main.py imports app/auth.py (this injects DATABASE_URL into os.environ)
3. auth.py calls stauth.Authenticate(credentials=..., auto_hash=False)
4. authenticator.login() renders username/password form
5. User submits → library compares entered password against stored bcrypt hash
6. On success: sets st.session_state["authentication_status"] = True
             sets st.session_state["role"] = user's role from credentials YAML
             sets a signed cookie (cookie_name, cookie_key, expiry_days)
7. On subsequent page loads: cookie is verified → user bypasses login form
8. logout() call on each page clears session_state and deletes cookie
```

### Critical: `auto_hash=False`
```python
authenticator = stauth.Authenticate(
    credentials=config["credentials"],
    cookie_name=config["cookie"]["name"],
    cookie_key=config["cookie"]["key"],
    cookie_expiry_days=config["cookie"]["expiry_days"],
    auto_hash=False,    # ← MUST be False
)
```

**Why:** When `auto_hash=True` (the 0.4.x default), the library treats stored passwords as plaintext and bcrypt-hashes them again at init time. Since the stored values are already bcrypt hashes, they get double-hashed and no entered password will ever match. This was the root cause of "incorrect password" failures with valid credentials.

### Password storage
Passwords are stored as bcrypt hashes in `credentials_yaml` Streamlit secret. Never stored as plaintext. bcrypt is the correct choice: it is salted, intentionally slow (work factor 12 by default), and universally trusted.

**Generating a hash:**
```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

**Do NOT use `streamlit_authenticator.Hasher` in 0.4.x** — its API changed and produces errors.

---

## 2. Authorisation / RBAC

Two roles exist:

| Role | Pages accessible | Capabilities |
|------|-----------------|--------------|
| `admin` | All 6 pages | Full CRUD, approve/reject deletion requests, manage duplicates, direct delete |
| `entry` | Pages 1–5 only | Add students, browse records, view dashboard, export, view import page |

**How role enforcement works:**
```python
# In every page that has restrictions:
require_role("admin", "entry")   # both roles allowed
require_role("admin")            # admin only

def require_role(*roles: str) -> bool:
    current = st.session_state.get("role", "")
    if current in roles:
        return True
    st.error("You do not have permission to view this page.")
    st.stop()   # ← halts Streamlit execution; page renders nothing further
    return False
```

**Important:** `st.stop()` is a Streamlit-specific mechanism that raises `StopException`. It prevents any further Python code on the page from executing. This is the correct approach for Streamlit apps — there is no middleware layer.

**Limitation:** Role checks happen at the Python level, not the routing level. A determined attacker who can run arbitrary Python (i.e. who has compromised the server) could bypass them. For the threat model of this application (trusted internal users, not public internet adversaries), this is acceptable.

### The deletion approval workflow
Entry-role users cannot delete records directly. They submit a deletion request (written to `deletion_requests` table with `status='pending'`). Admin users see pending requests on the Admin page and Approve (hard delete) or Reject. This provides:
- Audit trail (who requested, when, why, who approved)
- Prevention of accidental mass deletion by data-entry staff
- Admin oversight of data removal

---

## 3. Secrets Management

### Production (Streamlit Community Cloud)
Secrets are stored in Streamlit Cloud's encrypted secrets storage, accessible via `st.secrets`. Two secrets are required:

| Secret key | Content | Sensitivity |
|------------|---------|-------------|
| `DATABASE_URL` | Full Neon Postgres connection string including password | Critical — exposes entire database |
| `credentials_yaml` | Full YAML text with bcrypt-hashed passwords and cookie key | High — controls app access |

**Injection pattern:**
```python
# In auth.py, runs at import time before database.py loads:
try:
    _db_url = st.secrets.get("DATABASE_URL")
    if _db_url and not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = _db_url
except Exception:
    pass
```

### Local development
Secrets live in `.streamlit/secrets.toml` (gitignored). If absent, the app falls back to checking `.streamlit/credentials.yaml` (also gitignored) for auth, and uses SQLite for the database (no DATABASE_URL needed).

**Never commit:**
- `.streamlit/secrets.toml`
- `.streamlit/credentials.yaml`
- Any file containing the Neon connection string

The `.gitignore` currently excludes: `data/`, `*.db`, `.venv/`, `__pycache__/`, `.streamlit/credentials.yaml`, `.streamlit/secrets.toml`

### Cookie security
The cookie is signed with `cookie_key` from the credentials YAML. This key should be a long random string (32+ chars). If the key is compromised, attackers could forge valid session cookies. If you suspect compromise, change `cookie.key` in the Streamlit secrets — all existing sessions are immediately invalidated.

---

## 4. Database Security

### Connection security
Neon Postgres connection uses `sslmode=require` in the connection string. This enforces TLS for all traffic between the app and the database. Unencrypted connections are rejected by Neon.

### Access model
The connection string uses the `neondb_owner` role, which has full privileges on the database. There is no read-only role for reporting queries. This is a known limitation — ideally, the app would use a least-privilege role for read queries and a separate write role for inserts.

### SQL injection
All database queries use parameterised queries via `_execute(conn, sql, params)`. Raw string interpolation into SQL is not used anywhere in the codebase. This prevents SQL injection.

**Safe:**
```python
_execute(conn, "SELECT * FROM students WHERE national_id = ?", (nid,))
```

**Unsafe (never do this):**
```python
conn.execute(f"SELECT * FROM students WHERE national_id = '{nid}'")
```

---

## 5. Personal Data Handling

This platform stores PII (personally identifiable information) for ~1,800+ individuals:
- Full legal names
- National ID numbers (equivalent to a national identification card number)
- Dates of birth
- Genders
- Phone numbers
- Email addresses
- Family member details (names, NIDs, birthdays, relationships)

**Current data protection measures:**
- Database access requires Neon credentials (not publicly accessible)
- App access requires login (bcrypt-hashed passwords)
- TLS in transit (Neon's `sslmode=require`)
- No PII in application logs (Streamlit's default logging does not log query parameters)

**Current gaps:**
- No data retention policy is defined or enforced
- No encryption at rest beyond what Neon provides by default (Neon encrypts at rest)
- No audit log of who viewed which records (only deletion requests are logged)
- No GDPR/data protection compliance documentation
- The export function allows any authenticated user (including entry role) to download the full dataset as Excel

---

## 6. Attack Surface Analysis

| Surface | Risk | Current mitigation | Gap |
|---------|------|--------------------|-----|
| Login form | Brute force password guessing | bcrypt (slow hashing) | No rate limiting or lockout |
| Session cookie | Cookie theft/replay | Signed with cookie_key, expiry | No HttpOnly/Secure flags (Streamlit controls these) |
| Streamlit Cloud | Platform compromise | Anthropic/Streamlit manages | Dependent on vendor security |
| Neon database | Direct DB access | Password in secrets, SSL | neondb_owner has full privileges |
| Export page | Data exfiltration | Requires login | Entry role can download full dataset |
| Bulk import (CLI) | Malicious file | None | No file content validation; malformed Excel could trigger openpyxl bugs |
| `data_quality_report.xlsx` | PII in repo | It's in the repo root | **This file contains real student data and is committed to git** |

### The `data_quality_report.xlsx` risk
The file `data_quality_report.xlsx` was generated during the data quality analysis and committed to the repo. It contains real student national IDs, names, and dates of birth as part of the quality issue illustrations. This should be:
1. Removed from git history if the repo is ever made public
2. Added to `.gitignore` if future versions are regenerated
3. Shared via a secure channel (not GitHub) with the source organisation

---

## 7. Dev Mode Security Risk

If `.streamlit/credentials.yaml` does not exist and `st.secrets` does not contain `credentials_yaml`, the app runs in dev mode:
```python
st.session_state["role"] = "admin"
st.session_state["username"] = "dev"
return True, "Developer", "dev"
```

This means **anyone who can reach the Streamlit URL gets admin access with no authentication**. This is intentional for local development but catastrophic if triggered in production. It would happen if:
- Streamlit Cloud secrets are accidentally deleted
- A new deployment is made without configuring secrets first

**Mitigation:** The app shows a visible warning banner in dev mode. Monitor for this. Set up a Streamlit Cloud health alert if possible.

---

## 8. Recommended Security Improvements (Prioritised)

### High (address before sharing access with new users)
1. **Add login attempt rate limiting** — `streamlit-authenticator` doesn't provide this. Implement a per-IP or per-username counter in session state or a simple DB table.
2. **Restrict Export page** — consider requiring admin role to download full dataset, or at minimum log export events to `deletion_requests`-style audit table.
3. **Remove `data_quality_report.xlsx` from git or add to `.gitignore`** — it contains real PII.

### Medium
4. **Create a read-only Neon role** for read-only queries (reports, exports). The write role should only be used for inserts/updates. This limits the blast radius if the connection string is ever exposed.
5. **Add a "last login" audit table** — simple table tracking `(username, login_time, ip_address)`. Enables detection of unauthorized access.
6. **Document data retention policy** — how long are records kept? Is there a process for removing records when a student's scholarship ends?

### Nice-to-have
7. **Rotate Neon password periodically** — update in Streamlit secrets after rotation.
8. **Add CSP headers** — Streamlit doesn't support custom HTTP headers easily, but a reverse proxy (Nginx/Cloudflare) could add them.
