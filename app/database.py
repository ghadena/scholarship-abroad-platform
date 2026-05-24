"""
Database schema and helper functions for the Scholarship Abroad Platform.
SQLite is used for portability — no external server needed.

DB_PATH is read from the DB_PATH environment variable so that cloud deployments
(Render persistent disk) can override it without touching code.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

_default_db = Path(__file__).parent.parent / "data" / "scholarship.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(_default_db)))


SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    national_id     TEXT    NOT NULL UNIQUE CHECK (length(national_id) = 12),
    student_id      TEXT    NOT NULL UNIQUE,
    full_name       TEXT    NOT NULL,
    birthday        DATE    NOT NULL,
    gender          TEXT    CHECK (gender IN ('Male', 'Female')),
    birthday_flag   INTEGER NOT NULL DEFAULT 0,
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
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id_fk   INTEGER NOT NULL,
    full_name       TEXT    NOT NULL,
    national_id     TEXT    NOT NULL CHECK (length(national_id) = 12),
    birthday        DATE    NOT NULL,
    relationship    TEXT    NOT NULL CHECK (relationship IN
                              ('Spouse', 'Son', 'Daughter', 'Sibling')),
    gender          TEXT    CHECK (gender IN ('Male', 'Female')),
    birthday_flag   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id_fk) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS deletion_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE INDEX IF NOT EXISTS idx_students_country     ON students(country_abroad);
CREATE INDEX IF NOT EXISTS idx_students_level       ON students(study_level);
CREATE INDEX IF NOT EXISTS idx_students_start_date  ON students(start_date);
CREATE INDEX IF NOT EXISTS idx_accomp_student       ON accompaniments(student_id_fk);
"""

_DUPLICATE_COLUMNS = [
    ("duplicate_flag",   "INTEGER NOT NULL DEFAULT 0"),
    ("duplicate_reason", "TEXT"),
]


@contextmanager
def get_conn():
    """Context-managed SQLite connection with FK enforcement on."""
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


def _ensure_columns(conn):
    """Add duplicate_flag / duplicate_reason columns if they don't exist yet."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(students)")}
    for col_name, col_def in _DUPLICATE_COLUMNS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE students ADD COLUMN {col_name} {col_def}")


def init_db():
    """Create tables and run lightweight column migrations."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)


def insert_student(student_data: dict, accompaniments: list[dict] | None = None) -> int:
    """
    Insert one student and their accompaniments in a single transaction.
    Runs soft-duplicate flagging after insert.
    Returns the new student's database id.
    """
    from app.duplicates import flag_soft_duplicates

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO students (
                national_id, student_id, full_name, birthday, gender, birthday_flag,
                phone, email, country_abroad, study_level, study_field,
                start_date, end_date, decision_no
            ) VALUES (
                :national_id, :student_id, :full_name, :birthday, :gender, :birthday_flag,
                :phone, :email, :country_abroad, :study_level, :study_field,
                :start_date, :end_date, :decision_no
            )
            """,
            student_data,
        )
        student_pk = cur.lastrowid

        if accompaniments:
            for acc in accompaniments:
                acc["student_id_fk"] = student_pk
                conn.execute(
                    """
                    INSERT INTO accompaniments (
                        student_id_fk, full_name, national_id, birthday,
                        relationship, gender, birthday_flag
                    ) VALUES (
                        :student_id_fk, :full_name, :national_id, :birthday,
                        :relationship, :gender, :birthday_flag
                    )
                    """,
                    acc,
                )

        flag_soft_duplicates(conn)
        return student_pk


def fetch_students_df():
    """Return all students as a pandas DataFrame."""
    import pandas as pd
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM students ORDER BY created_at DESC", conn)


def fetch_accompaniments_df():
    """Return all accompaniments joined with their student's name/student_id."""
    import pandas as pd
    query = """
        SELECT a.*, s.student_id AS student_code, s.full_name AS student_name
        FROM accompaniments a
        JOIN students s ON s.id = a.student_id_fk
        ORDER BY a.student_id_fk, a.id
    """
    with get_conn() as conn:
        return pd.read_sql_query(query, conn)


def delete_student(student_pk: int):
    """Delete a student (cascade removes accompaniments and deletion_requests)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM students WHERE id = ?", (student_pk,))


def create_deletion_request(student_pk: int, requested_by: str, reason: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO deletion_requests (student_id_fk, requested_by, reason)
            VALUES (?, ?, ?)
            """,
            (student_pk, requested_by, reason),
        )


def fetch_deletion_requests_df(status: str | None = None):
    import pandas as pd
    where = "WHERE dr.status = ?" if status else ""
    params = (status,) if status else ()
    query = f"""
        SELECT dr.*, s.full_name AS student_name, s.student_id AS student_code
        FROM deletion_requests dr
        JOIN students s ON s.id = dr.student_id_fk
        {where}
        ORDER BY dr.created_at DESC
    """
    with get_conn() as conn:
        return pd.read_sql_query(query, conn, params=params)


def resolve_deletion_request(request_id: int, action: str, reviewed_by: str):
    """action must be 'approved' or 'rejected'. Approved also deletes the student."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT student_id_fk FROM deletion_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if row is None:
            return
        conn.execute(
            """
            UPDATE deletion_requests
            SET status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (action, reviewed_by, request_id),
        )
        if action == "approved":
            conn.execute("DELETE FROM students WHERE id = ?", (row["student_id_fk"],))


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
