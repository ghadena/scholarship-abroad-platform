"""
Duplicate detection and handling for the students table.
"""

import sqlite3


def find_duplicates(conn: sqlite3.Connection) -> dict:
    """
    Returns {"exact": [...], "soft": [...]}

    exact — all four of (national_id, student_id, full_name, birthday) match.
            Safe to auto-merge (keep lowest id, delete rest).

    soft  — any ONE of (national_id, student_id, full_name) matches but the
            rows are not exact duplicates. These need human review.

    Each entry is a dict with keys: id_a, id_b, name_a, name_b, and matched_on.
    """
    exact_query = """
        SELECT a.id AS id_a, b.id AS id_b,
               a.full_name AS name_a, b.full_name AS name_b
        FROM students a
        JOIN students b ON b.id > a.id
        WHERE a.national_id = b.national_id
          AND a.student_id  = b.student_id
          AND a.full_name   = b.full_name
          AND a.birthday    = b.birthday
    """

    soft_query = """
        SELECT a.id AS id_a, b.id AS id_b,
               a.full_name AS name_a, b.full_name AS name_b,
               CASE
                 WHEN a.national_id = b.national_id THEN 'national_id'
                 WHEN a.student_id  = b.student_id  THEN 'student_id'
                 ELSE 'full_name'
               END AS matched_on
        FROM students a
        JOIN students b ON b.id > a.id
        WHERE (
            a.national_id = b.national_id
            OR a.student_id  = b.student_id
            OR lower(trim(a.full_name)) = lower(trim(b.full_name))
        )
        AND NOT (
            a.national_id = b.national_id
            AND a.student_id  = b.student_id
            AND a.full_name   = b.full_name
            AND a.birthday    = b.birthday
        )
    """

    exact = [dict(r) for r in conn.execute(exact_query).fetchall()]
    soft  = [dict(r) for r in conn.execute(soft_query).fetchall()]
    return {"exact": exact, "soft": soft}


def flag_soft_duplicates(conn: sqlite3.Connection) -> None:
    """
    Set duplicate_flag = 1 and populate duplicate_reason for every student
    that is part of a soft-duplicate pair. Clears flags first so removals are
    reflected correctly on re-run.
    """
    # Reset all flags
    conn.execute("UPDATE students SET duplicate_flag = 0, duplicate_reason = NULL")

    soft_query = """
        SELECT a.id AS id_a, b.id AS id_b,
               CASE
                 WHEN a.national_id = b.national_id THEN 'national_id'
                 WHEN a.student_id  = b.student_id  THEN 'student_id'
                 ELSE 'full_name'
               END AS matched_on
        FROM students a
        JOIN students b ON b.id > a.id
        WHERE (
            a.national_id = b.national_id
            OR a.student_id  = b.student_id
            OR lower(trim(a.full_name)) = lower(trim(b.full_name))
        )
        AND NOT (
            a.national_id = b.national_id
            AND a.student_id  = b.student_id
            AND a.full_name   = b.full_name
            AND a.birthday    = b.birthday
        )
    """

    for row in conn.execute(soft_query).fetchall():
        reason = f"Matches another record on {row['matched_on']}"
        for sid in (row["id_a"], row["id_b"]):
            conn.execute(
                """
                UPDATE students
                SET duplicate_flag = 1, duplicate_reason = ?
                WHERE id = ?
                """,
                (reason, sid),
            )


def auto_remove_exact_duplicates(conn: sqlite3.Connection) -> int:
    """
    For each group of exact duplicates, keep the row with the lowest id and
    delete the rest. Returns the total number of rows deleted.
    """
    exact_query = """
        SELECT a.id AS id_a, b.id AS id_b
        FROM students a
        JOIN students b ON b.id > a.id
        WHERE a.national_id = b.national_id
          AND a.student_id  = b.student_id
          AND a.full_name   = b.full_name
          AND a.birthday    = b.birthday
    """
    rows = conn.execute(exact_query).fetchall()

    # Collect all ids that are NOT the minimum in their duplicate group.
    # We use a dict keyed by (national_id, student_id) to find the keeper.
    keeper_query = """
        SELECT min(id) AS keep_id, national_id, student_id
        FROM students
        GROUP BY national_id, student_id, full_name, birthday
        HAVING count(*) > 1
    """
    keepers = {(r["national_id"], r["student_id"]): r["keep_id"]
               for r in conn.execute(keeper_query).fetchall()}

    if not keepers:
        return 0

    to_delete = []
    for r in rows:
        # id_b is always > id_a because of the JOIN condition, so id_a is the keeper
        to_delete.append(r["id_b"])

    deleted = 0
    for sid in set(to_delete):
        conn.execute("DELETE FROM students WHERE id = ?", (sid,))
        deleted += 1

    # Re-run flag pass after cleanup
    flag_soft_duplicates(conn)
    return deleted
