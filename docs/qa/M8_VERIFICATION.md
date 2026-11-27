# Milestone M8 Verification & Pilot Report

**Verifier:** `@qa-verifier`  
**Scope:** End-to-end verification across Milestones M0–M8 (`PRODUCT.md` §§1–16)

---

## 1. Automated Verification Summary

| Suite / Check | Working Directory | Command | Result |
|---|---|---|---|
| Backend Lint & Formatting | `backend/` | `python -m ruff check app migrations tests` | **Passed** (`All checks passed!`) |
| Backend Full Test Suite | `backend/` | `python -m pytest -v --tb=short` | **137 passed, 0 failed** (`28.24s`, 14 warnings) |
| Frontend Unit Tests | `frontend/` | `npm test` (`tsx --test tests/*.test.ts`) | **10 passed, 0 failed** (`314.79ms`) |
| Frontend TypeScript Check | `frontend/` | `npx tsc --noEmit` | **Passed** (exit `0`) |
| Frontend ESLint | `frontend/` | `npm run lint` (`next lint`) | **Passed** (`No ESLint warnings or errors`) |
| Frontend Production Build | `frontend/` | `npm run build` (`next build`) | **Passed** (compiled in `3.0s`; `12` static + `5` dynamic routes) |

---

## 2. Security & Privacy Audit (`backend/tests/security/test_security_audit.py`)

All 3 security audit tests passed:

1. **Frontend Secret Scan (`test_frontend_source_contains_no_gemini_api_keys_or_secrets`)**
   - Scanned `frontend/` (`*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.mjs`, `*.json`, excluding `node_modules` and `.next`).
   - Verified zero occurrences of `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or `AIza...` patterns.
2. **Private Storage Traversal Hardening (`test_local_private_storage_rejects_traversal_and_absolute_paths`)**
   - Verified `LocalPrivateStorage._resolve_key` rejects `../outside.pdf`, embedded `users/a/../../outside.pdf`, `..\windows_escape.pdf`, `C:\Windows\System32\drivers\etc\hosts`, null-byte keys (`\x00`), UNC prefixes, and empty keys with `ValueError`.
   - Verified leading-slash POSIX keys resolve strictly within `storage.root`.
   - *Hardening fix applied during M8:* `@document-engineer` updated `backend/app/services/document_ingestion/storage.py` to reject `.`/`..` segments, `\x00`, UNC paths, and drive-letter prefixes prior to `.resolve()`.
3. **Full Surface Leak, Static Mount & Ownership Audit (`test_full_surface_no_storage_leaks_no_static_mount_no_answer_leaks_and_403s`)**
   - Verified `storage_key` and local filesystem storage paths do not appear anywhere in `/documents`, `/documents/{id}`, `/documents/{id}/pages`, `/documents/{id}/notes`, `/notes/{id}`, `/questions`, `/questions/{id}`, `/tests`, `/tests/{id}/start`, `/attempts/{id}/current`, or `/dashboard`.
   - Verified private storage paths under `/storage/...`, `/static/...`, and `/api/v1/storage/...` return `404` (never statically served).
   - Verified active-test endpoints (`GET /tests/{id}`, `POST /tests/{id}/start`, `GET /attempts/{id}/current`) never expose `correct_option_key`, `correct_answer_data`, `is_correct`, `answer_key`, or `explanation`.
   - Verified cross-user `403` isolation across all 31 user-owned resource routes (`documents`, `pages`, `assets`, `coverage`, `jobs`, `extract-knowledge`, `classification`, `knowledge`, `topics`, `facts`, `notes`, `pyq-patterns`, `questions`, `tests`, `attempts`, `analysis`, `improvement-plan`) plus `404` on non-existent UUIDs.

---

## 3. 3-PDF SSC CHSL Pilot End-to-End Simulation (`backend/tests/integration/test_pilot_e2e.py`)

`test_three_pdf_ssc_chsl_pilot_end_to_end` executed the complete `PRODUCT.md` §16 journey offline with `MockLLMProvider`, `PilotOCRAdapter`, and deterministic `PilotClock` (`httpx` outbound HTTP transports blocked):

1. **Three Realistic PDFs Uploaded & Extracted:**
   - **PDF 1 (Text Maths):** Extracted page text, formulas, and MCQs (`Percentages`).
   - **PDF 2 (Table + Vector Diagram):** Extracted structured table (`tables_extracted >= 1` via `pdfplumber`) and cropped vector geometry diagram (`images_extracted >= 1` via PyMuPDF).
   - **PDF 3 (Scanned Image-Only):** Flagged `pages_requiring_ocr == 1` under `NullOCRAdapter`; recovered text via `ocr_retry` with `PilotOCRAdapter` (`pages_extracted_ocr == 1`, `pages_requiring_ocr == 0`).
2. **Knowledge, Notes & Question Bank:**
   - Extracted grounded facts, concepts, and 6 verified MCQs across all 3 PDFs.
   - Generated `detailed`, `quick_revision`, and `strategy_sheet` notes; verified `quick_revision` text length is strictly shorter than `detailed`.
3. **Timed 35s Speed Challenge & Hand-Calculated Scoring:**
   - Verified simulated mid-test refresh at `t+15s` preserves `20s` remaining (`question_remaining_seconds == 20`).
   - Forced 1 timeout past `35s + 1500ms` grace (`409 QUESTION_TIMED_OUT`), plus 1 correct (`+2.00`) and 3 incorrect (`-0.50` each).
   - Verified `/submit` and `/results` match exact hand-calculated `Decimal` score `0.50 / 10.00` and `25.00%` attempted accuracy.
4. **Improvement Plan, Targeted Retest & Cross-Attempt Deltas:**
   - Generated rule-based improvement plan (`concept_revision` triggered).
   - Built & completed a 5-question Targeted Practice retest (`POST /api/v1/performance/targeted-practice`, `10.00 / 10.00`, `100.00%` accuracy).
   - Verified `/performance/topics/{topic_id}/trends` shows `[25.00%, 100.00%]`, `/attempts/{id}/analysis` reports `+75.00%` attempt-over-attempt delta, and `/performance/overview` reports `+41.67%` cumulative delta (`25.00%` -> `66.67%`).

---

## 4. Known Non-Blocking Warnings / Environment Notes

- **Backend pytest warnings (`14`):** `python-multipart` pending deprecation from Starlette, `PytestCollectionWarning` for SQLAlchemy ORM `Test`/`TestQuestion` classes imported into integration tests, and Alembic `path_separator` deprecation notice. None affect runtime correctness.
- **Database engine in test/dev:** Executed against isolated per-test SQLite databases with dialect-agnostic SQLAlchemy models and Alembic upgrade/downgrade/upgrade migration verification (`test_alembic_upgrade_downgrade_upgrade_cycle`). Live PostgreSQL 16 and live Gemini API (`@pytest.mark.live_ai`) were excluded from offline CI by design.
- **Frontend Next.js build note:** `next lint` deprecation notice in Next.js 15.5.29 and workspace lockfile root warning from parent directory `package-lock.json`; zero lint errors/warnings and zero TypeScript errors.
