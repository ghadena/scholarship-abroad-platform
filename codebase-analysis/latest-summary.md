# Codebase Analysis — Latest Summary

**File:** `codebase-analysis-2026-05-25.html`  
**Generated:** 2026-05-25  
**Git commit:** `e1a9485` — docs: handover, README, DEPLOYMENT, skills, codebase analysis  
**Branch:** main

---

## Module Inventory

| Module | Type | Status |
|--------|------|--------|
| app/main.py | Entry point | OK |
| app/auth.py | Core — Auth | OK (critical import ordering) |
| app/database.py | Core — DB layer | OK (dual Postgres/SQLite; 'Unknown' in relationship constraint) |
| app/validation.py | Core — Validation | OK (14 tests passing) |
| app/duplicates.py | Core — Duplicates | OK (O(n²) — monitor at scale) |
| app/report.py | Core — PDF Report | OK (bilingual AR/EN; exclude_overdue param; outlier sections) |
| app/importer.py | Orphaned module | ⚰ Dead — SQLite-only, no callers — delete this |
| app/pages/1_Data_Entry.py | Page | OK |
| app/pages/2_Records.py | Page | OK |
| app/pages/3_Dashboard.py | Page | 🐛 line 22: uses fetch_students_df() — shows placeholder data |
| app/pages/4_Import.py | Page | OK (info page) |
| app/pages/5_Export_Report.py | Page | OK (exclude_overdue checkbox; Specialization filter option) |
| app/pages/6_Admin.py | Page | OK (admin-only) |
| scripts/bulk_import.py | CLI script | OK (flags NID dups; ? suffix on student_id conflict; no remaining_study_months) |
| scripts/generate_data_quality_report.py | CLI script | OK (catches ? suffix student_ids in Sheet 2) |
| scripts/find_missing_students.py | CLI script | OK (diff DB vs Excel; exports missing rows) |
| scripts/import_missing_students.py | CLI script | OK (import missing_students_YYYY-MM-DD.xlsx format) |
| scripts/check_db_count.py | CLI script | OK (quick row count check) |
| scripts/fix_specialization.py | CLI script | One-off diagnostic, run complete — no further use |
| tests/ (2 active files) | Tests | 14 passing; test_importer.py stale (tests dead importer.py) |

## Database Tables

| Table | Rows (as of 2026-05-25) | Notes |
|-------|------------------------|-------|
| students | 1,854 | Placeholder study data overridden by enrichment at read time |
| accompaniments | 8,100+ | No UNIQUE constraint — TRUNCATE before reimport |
| student_enrichment | 1,860 | ~6 extra rows vs students (historical oddity); remaining_study_months always calculated dynamically |
| deletion_requests | — | Audit trail for deletions |

## Open Issues (priority order)

1. **HIGH** — Wipe + reimport on live Neon DB needed (use DEPLOYMENT.md procedure)
2. **HIGH** — `3_Dashboard.py:22` uses `fetch_students_df()` instead of `fetch_full_students_df()` → placeholder values in all charts
3. **MEDIUM** — `app/importer.py` is dead SQLite-only code — delete it (and stale `test_importer.py`)
4. **MEDIUM** — No student edit/update UI — must edit via Neon SQL Editor or delete+re-add
5. **MEDIUM** — `accompaniments` has no UNIQUE constraint — re-running import without TRUNCATE creates duplicates
6. **LOW** — `updated_at` column on students never auto-updates (no trigger)
7. **LOW** — No automated backup job — manual `pg_dump` before every bulk import

## Architecture Highlights

- **Critical path:** `auth.py` MUST import before `database.py` on every page (injects DATABASE_URL into os.environ at module import time)
- **Dual-mode DB:** `_USE_POSTGRES` set at module import time — immutable for process lifetime
- **Enrichment merge:** COALESCE LEFT JOIN is the canonical data view — always use `fetch_full_students_df()` for analytics
- **Bulk import:** Per-row SAVEPOINTs isolate Postgres constraint violations; NID dups flagged; student_id conflicts get `?` suffix + flag
- **`remaining_study_months`:** NOT stored — always calculated as `(end_date - today).dt.days / 30.44` at runtime
- **Specialization:** Only in `student_enrichment.certificate` — NOT in `students.study_level` CHECK constraint
- **`exclude_overdue`:** Report parameter; when True strips `end_date < today` students before all calculations
- **Outlier sections:** Report includes long-study (5+ years) and large-family (8+ members) sections

## Data Flow

```
new_excel.xlsx
  ├── "student data"      → students table         (placeholder study fields)
  ├── "more student data" → student_enrichment       (authoritative study fields)
  └── "family data"       → accompaniments table

Canonical read: fetch_full_students_df()
  = students LEFT JOIN student_enrichment ON national_id
  with COALESCE(enrichment, placeholder) for all study fields
  + remaining_study_months calculated dynamically

Report: build_executive_report(students_df, family_df, enrich_df, arabic, exclude_overdue)
  → PDF via ReportLab + matplotlib (bilingual AR/EN)

Quality check: generate_data_quality_report.py → 7-sheet Excel
```

## How to regenerate this map

Run the `/enterprise-docs` slash command in Claude Code from this repo.
