# Codebase Analysis — Latest Summary

**File:** `codebase-analysis-2026-05-24-0000.html`  
**Generated:** 2026-05-24  
**Git commit:** `a7aa4cd` — Add technical handover document (2026-05-24)  
**Branch:** main

---

## Module Inventory

| Module | Type | Status |
|--------|------|--------|
| app/main.py | Entry point | OK |
| app/auth.py | Core — Auth | OK (critical import ordering) |
| app/database.py | Core — DB layer | OK (dual Postgres/SQLite) |
| app/validation.py | Core — Validation | OK (14 tests passing) |
| app/duplicates.py | Core — Duplicates | OK (O(n²) — monitor at scale) |
| app/report.py | Core — PDF Report | ⚠ legacy alias issue |
| app/importer.py | Orphaned module | ⚰ Dead — SQLite-only, no callers |
| app/pages/1_Data_Entry.py | Page | OK |
| app/pages/2_Records.py | Page | OK (should use full_students_df) |
| app/pages/3_Dashboard.py | Page | 🐛 BUG line 22 |
| app/pages/4_Import.py | Page | OK (info-only now) |
| app/pages/5_Export_Report.py | Page | OK (filters + PDF working) |
| app/pages/6_Admin.py | Page | OK (admin-only) |
| scripts/bulk_import.py | CLI script | OK (idempotent for students+enrichment) |
| tests/ (3 files) | Tests | 14 passing; 2 files stale |

## Database Tables

| Table | Rows | Notes |
|-------|------|-------|
| students | 1,822 | ~1,800 have placeholder study data from bulk import |
| accompaniments | 7,748 | No UNIQUE constraint — re-running import creates dupes |
| student_enrichment | 1,860 | 14 students in students have no match here |
| deletion_requests | — | Audit trail for deletions |

## Open Issues (priority order)

1. **HIGH** — `3_Dashboard.py:22` uses `fetch_students_df()` instead of `fetch_full_students_df()` → placeholder values in all charts
2. **HIGH** (if public) — `data_quality_report.xlsx` contains real PII committed to git
3. **MEDIUM** — `importer.py` is dead SQLite-only code with stale tests
4. **MEDIUM** — `build_quarterly_report` alias passes empty `enrich_df`
5. **MEDIUM** — No student edit/update UI
6. **MEDIUM** — `remaining_study_months` is stale (static from import date)
7. **LOW** — `updated_at` column never auto-updated
8. **LOW** — `DEPLOYMENT.md` describes SQLite, not Neon

## Architecture Highlights

- **Critical path:** `auth.py` MUST import before `database.py` on every page (injects DATABASE_URL)
- **Dual-mode DB:** `_USE_POSTGRES` set at module import time — immutable for process lifetime
- **Enrichment merge:** COALESCE LEFT JOIN is the canonical data view — always use `fetch_full_students_df()` for analytics
- **Bulk import:** Per-row SAVEPOINTs isolate Postgres constraint violations — safe to fail individual rows

## How to regenerate this map

Run the `/enterprise-docs` slash command in Claude Code from this repo.
