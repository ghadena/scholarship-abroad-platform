"""
Database helpers for the Scholarship Abroad Platform.

Uses Postgres (via psycopg2) when DATABASE_URL is set — this is the Neon
connection string injected as a Streamlit secret or environment variable.
Falls back to SQLite for local development when DATABASE_URL is absent.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ── SQLite fallback path (local dev only) ─────────────────────────────────────
_default_db = Path(__file__).parent.parent / "data" / "scholarship.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(_default_db)))

_USE_POSTGRES = bool(DATABASE_URL)


# ── Schema ────────────────────────────────────────────────────────────────────
# Written in Postgres-compatible SQL.
# SQLite accepts all of it except SERIAL — we swap that at runtime.

_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS students (
    id              SERIAL PRIMARY KEY,
    national_id     TEXT    NOT NULL UNIQUE CHECK (char_length(national_id) = 12),
    student_id      TEXT    NOT NULL UNIQUE,
    full_name       TEXT    NOT NULL,
    birthday        DATE    NOT NULL,
    gender          TEXT    CHECK (gender IN ('Male', 'Female')),
    birthday_flag   INTEGER NOT NULL DEFAULT 0,
    duplicate_flag  INTEGER NOT NULL DEFAULT 0,
    duplicate_reason TEXT,
    phone           TEXT,
    email           TEXT,
    country_abroad  TEXT    NOT NULL,
    study_level     TEXT    NOT NULL CHECK (study_level IN
                              ('Bachelors', 'Masters', 'Doctorate', 'Certificate')),
    study_field     TEXT    NOT NULL,
    start_date      DATE    NOT NULL,
    end_date        DATE    NOT NULL,
    decision_no     TEXT    NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS accompaniments (
    id              SERIAL PRIMARY KEY,
    student_id_fk   INTEGER NOT NULL,
    full_name       TEXT    NOT NULL,
    national_id     TEXT    NOT NULL CHECK (char_length(national_id) = 12),
    birthday        DATE    NOT NULL,
    relationship    TEXT    NOT NULL CHECK (relationship IN
                              ('Spouse', 'Son', 'Daughter', 'Sibling')),
    gender          TEXT    CHECK (gender IN ('Male', 'Female')),
    birthday_flag   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id_fk) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS deletion_requests (
    id              SERIAL PRIMARY KEY,
    student_id_fk   INTEGER NOT NULL,
    requested_by    TEXT NOT NULL,
    reason          TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','approved','rejected')),
    reviewed_by     TEXT,
    reviewed_at     TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id_fk) REFERENCES students(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_students_country    ON students(country_abroad);
CREATE INDEX IF NOT EXISTS idx_students_level      ON students(study_level);
CREATE INDEX IF NOT EXISTS idx_students_start_date ON students(start_date);
CREATE INDEX IF NOT EXISTS idx_accomp_student      ON accompaniments(student_id_fk);
"""

_SCHEMA_SQLITE = _SCHEMA_PG.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT") \
                            .replace("char_length(", "length(")


# ── Connection context managers ───────────────────────────────────────────────

@contextmanager
def get_conn():
    if _USE_POSTGRES:
        with _pg_conn() as conn:
            yield conn
    else:
        with _sqlite_conn() as conn:
            yield conn


@contextmanager
def _pg_conn():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    # Use RealDictCursor so rows behave like dicts (same as sqlite3.Row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _sqlite_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _placeholder(n: int) -> str:
    """Return %s placeholders for Postgres, ? for SQLite."""
    ph = "%s" if _USE_POSTGRES else "?"
    return ", ".join([ph] * n)


def _execute(conn, sql: str, params=()) -> "cursor":
    """Run a query with the right placeholder style."""
    if _USE_POSTGRES:
        sql = sql.replace("?", "%s")
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _executemany(conn, sql: str, rows):
    if _USE_POSTGRES:
        sql = sql.replace("?", "%s")
    cur = conn.cursor()
    cur.executemany(sql, rows)
    return cur


# ── Schema init ───────────────────────────────────────────────────────────────

def init_db():
    schema = _SCHEMA_PG if _USE_POSTGRES else _SCHEMA_SQLITE
    with get_conn() as conn:
        if _USE_POSTGRES:
            cur = conn.cursor()
            # Split on ; and run each statement individually
            for stmt in [s.strip() for s in schema.split(";") if s.strip()]:
                cur.execute(stmt)
        else:
            conn.executescript(schema)
        _ensure_columns(conn)


def _ensure_columns(conn):
    """Add duplicate_flag / duplicate_reason if missing (SQLite legacy migration)."""
    if _USE_POSTGRES:
        cur = conn.cursor()
        for col, coltype in [("duplicate_flag", "INTEGER NOT NULL DEFAULT 0"),
                             ("duplicate_reason", "TEXT")]:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name='students' AND column_name=%s
            """, (col,))
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE students ADD COLUMN {col} {coltype}")
    else:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(students)")}
        for col, coldef in [("duplicate_flag", "INTEGER NOT NULL DEFAULT 0"),
                            ("duplicate_reason", "TEXT")]:
            if col not in existing:
                conn.execute(f"ALTER TABLE students ADD COLUMN {col} {coldef}")


# ── CRUD ──────────────────────────────────────────────────────────────────────

def insert_student(student_data: dict, accompaniments: list[dict] | None = None) -> int:
    from app.duplicates import flag_soft_duplicates

    with get_conn() as conn:
        fields = ("national_id", "student_id", "full_name", "birthday", "gender",
                  "birthday_flag", "phone", "email", "country_abroad", "study_level",
                  "study_field", "start_date", "end_date", "decision_no")
        vals = tuple(student_data.get(f) for f in fields)
        ph = _placeholder(len(fields))

        if _USE_POSTGRES:
            sql = f"""
                INSERT INTO students ({', '.join(fields)})
                VALUES ({ph}) RETURNING id
            """
            cur = _execute(conn, sql, vals)
            student_pk = cur.fetchone()[0]
        else:
            sql = f"""
                INSERT INTO students ({', '.join(fields)})
                VALUES ({ph})
            """
            cur = _execute(conn, sql, vals)
            student_pk = cur.lastrowid

        if accompaniments:
            acc_fields = ("student_id_fk", "full_name", "national_id", "birthday",
                          "relationship", "gender", "birthday_flag")
            acc_ph = _placeholder(len(acc_fields))
            acc_sql = f"""
                INSERT INTO accompaniments ({', '.join(acc_fields)})
                VALUES ({acc_ph})
            """
            for acc in accompaniments:
                acc["student_id_fk"] = student_pk
                _execute(conn, acc_sql, tuple(acc.get(f) for f in acc_fields))

        flag_soft_duplicates(conn)
        return student_pk


def fetch_students_df():
    import pandas as pd
    with get_conn() as conn:
        if _USE_POSTGRES:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM students ORDER BY created_at DESC")
            rows = cur.fetchall()
            return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
        else:
            return pd.read_sql_query("SELECT * FROM students ORDER BY created_at DESC", conn)


def fetch_accompaniments_df():
    import pandas as pd
    sql = """
        SELECT a.*, s.student_id AS student_code, s.full_name AS student_name
        FROM accompaniments a
        JOIN students s ON s.id = a.student_id_fk
        ORDER BY a.student_id_fk, a.id
    """
    with get_conn() as conn:
        if _USE_POSTGRES:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql)
            rows = cur.fetchall()
            return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
        else:
            return pd.read_sql_query(sql, conn)


def delete_student(student_pk: int):
    with get_conn() as conn:
        _execute(conn, "DELETE FROM students WHERE id = ?", (student_pk,))


def create_deletion_request(student_pk: int, requested_by: str, reason: str):
    with get_conn() as conn:
        _execute(conn,
            "INSERT INTO deletion_requests (student_id_fk, requested_by, reason) VALUES (?, ?, ?)",
            (student_pk, requested_by, reason),
        )


def fetch_deletion_requests_df(status: str | None = None):
    import pandas as pd
    where = "WHERE dr.status = ?" if status else ""
    params = (status,) if status else ()
    sql = f"""
        SELECT dr.*, s.full_name AS student_name, s.student_id AS student_code
        FROM deletion_requests dr
        JOIN students s ON s.id = dr.student_id_fk
        {where}
        ORDER BY dr.created_at DESC
    """
    with get_conn() as conn:
        if _USE_POSTGRES:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql.replace("?", "%s"), params)
            rows = cur.fetchall()
            return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
        else:
            return pd.read_sql_query(sql, conn, params=params)


def resolve_deletion_request(request_id: int, action: str, reviewed_by: str):
    with get_conn() as conn:
        cur = _execute(conn,
            "SELECT student_id_fk FROM deletion_requests WHERE id = ?", (request_id,))
        row = cur.fetchone()
        if row is None:
            return
        student_fk = row[0] if not _USE_POSTGRES else row["student_id_fk"]
        _execute(conn,
            """UPDATE deletion_requests
               SET status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (action, reviewed_by, request_id),
        )
        if action == "approved":
            _execute(conn, "DELETE FROM students WHERE id = ?", (student_fk,))


if __name__ == "__main__":
    init_db()
    print(f"Database initialized. Postgres={_USE_POSTGRES}")
