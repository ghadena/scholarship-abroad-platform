"""Quick DB count check."""
import os, sys
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("Set DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM students")
print(f"students table:          {cur.fetchone()[0]:,}")

cur.execute("SELECT COUNT(*) FROM accompaniments")
print(f"accompaniments table:    {cur.fetchone()[0]:,}")

cur.execute("SELECT COUNT(*) FROM student_enrichment")
print(f"student_enrichment table:{cur.fetchone()[0]:,}")

# Check if any students table has a deleted_at or is_deleted column
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='students'")
cols = [r[0] for r in cur.fetchall()]
print(f"\nstudents columns: {cols}")

cur.close()
conn.close()
