"""
Duplicate detection and handling for the students table.
Works with both Postgres and SQLite connections.
"""

from app.database import _USE_POSTGRES, _execute


def find_duplicates(conn) -> dict:
    """
    Returns {"exact": [...], "soft": [...]}

    exact — all four of (national_id, student_id, full_name, birthday) match.
    soft  — any ONE of (national_id, student_id, full_name) matches but rows differ.
    """
    exact_sql = """
        SELECT a.id AS id_a, b.id AS id_b,
               a.full_name AS name_a, b.full_name AS name_b
        FROM students a
        JOIN students b ON b.id > a.id
        WHERE a.national_id = b.national_id
          AND a.student_id  = b.student_id
          AND a.full_name   = b.full_name
          AND a.birthday    = b.birthday
    """
    soft_sql = """
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

    def fetch(sql):
        cur = _execute(conn, sql)
        rows = cur.fetchall()
        if _USE_POSTGRES:
            return [dict(r) for r in rows]
        return [dict(r) for r in rows]

    return {"exact": fetch(exact_sql), "soft": fetch(soft_sql)}


def flag_soft_duplicates(conn) -> None:
    """Reset duplicate flags then set them for all soft-duplicate pairs."""
    _execute(conn, "UPDATE students SET duplicate_flag = 0, duplicate_reason = NULL")

    soft_sql = """
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
    cur = _execute(conn, soft_sql)
    rows = cur.fetchall()

    for row in rows:
        if _USE_POSTGRES:
            id_a, id_b, matched_on = row["id_a"], row["id_b"], row["matched_on"]
        else:
            id_a, id_b, matched_on = row["id_a"], row["id_b"], row["matched_on"]
        reason = f"Matches another record on {matched_on}"
        for sid in (id_a, id_b):
            _execute(conn,
                "UPDATE students SET duplicate_flag = 1, duplicate_reason = ? WHERE id = ?",
                (reason, sid),
            )


def auto_remove_exact_duplicates(conn) -> int:
    """Keep the lowest id in each exact-duplicate group, delete the rest."""
    exact_sql = """
        SELECT a.id AS id_a, b.id AS id_b
        FROM students a
        JOIN students b ON b.id > a.id
        WHERE a.national_id = b.national_id
          AND a.student_id  = b.student_id
          AND a.full_name   = b.full_name
          AND a.birthday    = b.birthday
    """
    cur = _execute(conn, exact_sql)
    rows = cur.fetchall()

    if not rows:
        return 0

    # id_b is always > id_a — so id_b is the duplicate to remove
    to_delete = set()
    for row in rows:
        to_delete.add(row["id_b"] if _USE_POSTGRES else row["id_b"])

    deleted = 0
    for sid in to_delete:
        _execute(conn, "DELETE FROM students WHERE id = ?", (sid,))
        deleted += 1

    flag_soft_duplicates(conn)
    return deleted
