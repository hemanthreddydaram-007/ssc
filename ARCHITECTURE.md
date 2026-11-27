# ARCHITECTURE.md — AI Exam Coach

**Status:** Phase 1 Approved Baseline (Pending M0 Kickoff)  
**Source of Truth:** [PRODUCT.md](file:///c:/Users/DARAM%20%20HEMANTH%20REDDY/Desktop/ssc/PRODUCT.md)

---

## 1. Repository & Environment Assessment

- **Repository state:** Clean reset at commit `c189973` (`Remove all files to start fresh`). Only `PRODUCT.md` (1,783 lines; canonical spec) and an empty `Unconfirmed 979309.crdownload` (0-byte leftover file to ignore/clean in M0) exist in the workspace. No `backend/`, `frontend/`, or `storage/` directories exist yet.
- **Local runtimes verified:** Python `3.11.9`, Node `v22.23.3`, npm `10.9.9`, Docker `29.6.2`.
- **Host gaps to account for:** `psql`, `tesseract`, and `pdftoppm` are not installed on `PATH`, and `pdfplumber`, `alembic`, `psycopg[binary]`, `sympy`, `rapidfuzz`, `ruff`, and `mypy` need to be declared in `backend/pyproject.toml`.
  - **PostgreSQL strategy:** Use Docker Compose (`postgres:16`) for local PostgreSQL + Alembic migrations. Keep SQLAlchemy 2.0 column types dialect-agnostic (`Uuid`, `JSON` / `JSONVariant`, `Numeric(8, 2)`, `DateTime(timezone=True)`) so unit tests can also run fast without external DB dependencies where appropriate.
  - **Windows PDF/OCR strategy:** Use PyMuPDF (`get_pixmap()`) instead of `pdftoppm`, pure-Python magic-byte validation instead of `libmagic`, and a replaceable `OCRAdapter` (`NullOCRAdapter` default in M2, `GeminiVisionOCRAdapter` via `LLMProvider`, optional `RapidOCRAdapter` on `onnxruntime`) instead of requiring native `tesseract.exe`.

---

## 2. System Architecture (Modular Monolith)

```text
+-------------------------------------------------------------------------+
|                    Next.js App Router + TypeScript UI                    |
|  Dashboard | Library | Doc Workspace | Notes | Bank | Tests | Perf      |
|  (TanStack Query, Tailwind + shadcn/ui, KaTeX, Server-Synced Timer)     |
+------------------------------------+------------------------------------+
                                     | REST / JSON + Multipart (/api/v1)
                                     v
+-------------------------------------------------------------------------+
|                        FastAPI Modular Monolith                          |
|                                                                         |
|  +------------------+   +-------------------+   +--------------------+  |
|  | Document         |   | AI & Learning     |   | Assessment         |  |
|  | Ingestion &      |-->| Classification,   |-->| Question Bank,     |  |
|  | Extraction       |   | Knowledge & Notes |   | Validator & Timer  |  |
|  +--------+---------+   +---------+---------+   +---------+----------+  |
|           |                       |                       |             |
|           |                       v                       v             |
|           |             +-------------------+   +--------------------+  |
|           |             | LLMProvider       |   | Performance        |  |
|           |             | (Gemini Adapter + |<--| Analytics, Rules & |  |
|           |             |  1-Retry Repair)  |   | Improvement Plan   |  |
|           |             +-------------------+   +--------------------+  |
|           |                                                             |
|  +--------v---------+   +--------------------------------------------+  |
|  | Private Storage  |   | PostgreSQL (SQLAlchemy 2 + Alembic)        |  |
|  | ./storage/users/ |   | Documents, Knowledge, Questions, Attempts, |  |
|  +------------------+   | Topic Performance, Jobs                    |  +
|                         +--------------------------------------------+  |
+-------------------------------------------------------------------------+
```

### Key Architectural Decisions & Conflict Resolutions

1. **Dialect-agnostic PostgreSQL-first ORM:** Primary runtime DB is PostgreSQL 16 via Docker Compose. Models avoid Postgres-only `ARRAY` or bare `JSONB` literals so tests remain portable.
2. **Ownership & Auth Dependency:** Every user-owned table stores `user_id`. A central `get_current_user` dependency serves a seeded `LOCAL_DEFAULT_USER_ID` in single-user dev mode and supports `X-User-Id` switching only when `AUTH_MODE=dev_header` (test/dev), enabling real multi-user ownership tests (`403`/`404`) from M1 before public auth is wired.
3. **Upload Deduplication & Retention:**
   - Duplicate `(user_id, sha256)` on non-deleted documents returns `409 Conflict` with `existing_document_id` (overridable via `allow_duplicate=true`).
   - `DELETE /api/v1/documents/{id}` defaults to `cascade_derived=true` (removes private files, pages, chunks, assets, jobs, facts, concepts, notes), while `questions` referenced by `test_questions` have `document_id` set to `NULL` (`ON DELETE SET NULL`) to preserve historical `tests` and `attempts`.
4. **Honest Job Stages (No Fake Percentages):** `processing_jobs` records discrete stage statuses (`pending | running | completed | failed | skipped`) and real item counters (`processed_items / total_items`).
5. **Single `LLMProvider` Boundary:** All Gemini SDK (`google-genai`) calls live exclusively inside `backend/app/ai/gemini_provider.py`. Extraction, notes, question generation/verification, OCR vision fallback, and AI coaching all call `LLMProvider`.
6. **Single-Pass Question Candidate Handoff:** For PYQ/mixed PDFs, `@learning-engineer`'s chunk extractor emits raw `ExtractedQuestionCandidate` payloads and hands them to `@assessment-engineer`'s `QuestionIngestionService` / `QuestionValidator` for deterministic math checks, option uniqueness, deduplication, and persistence.
7. **Server-Authoritative Timing & Active-Test Security:**
   - `EXPIRY_GRACE_MS = 1500` server grace for network jitter; submissions beyond `expires_at + 1500ms` are recorded as `timed_out` (Speed Challenge) or auto-submitted (Exam Simulation).
   - `GET /api/v1/attempts/{id}/current` auto-closes any expired question/attempt before returning `server_now`, `expires_at`, and active cursor.
   - Active-test DTOs strictly omit `correct_answer_data`, `correct_option_key`, `is_correct`, and `explanation`. In `learning_mode` with `after_question`, `POST /responses` locks that single response and returns its explanation only.
8. **Route Split on Attempts vs. Performance:** `@assessment-engineer` owns `/api/v1/attempts/*` including `/results` (and triggers `TopicAggregator` on submit); `@performance-engineer` owns `/api/v1/attempts/{id}/analysis`, `/improvement-plan`, and `/api/v1/performance/*`.

---

## 3. Component Boundaries

| Component | Owner | Reads | Writes | Exposes to Peers |
|---|---|---|---|---|
| **Core / DB / Migrations** | `@coordinator` | All | Schema, migrations, config, `users`, router wiring | `get_db`, `get_current_user`, `Settings`, ORM models |
| **Document Ingestion & Extraction** | `@document-engineer` | `documents`, `document_pages`, `facts`/`concepts`/`questions` (counts only) | `documents`, `document_pages`, `document_chunks`, `document_assets`, `processing_jobs`, private `storage/` | `DocumentReadService` (pages, chunks, assets), `CoverageAuditService` |
| **AI & Learning Engine** | `@learning-engineer` | `documents`, `document_pages`, `document_chunks`, `exam_configs` | `topics`, `concepts`, `facts`, `notes`, `ai_generation_runs` | `LLMProvider`, `SubjectAdapterRegistry`, `KnowledgeReadService`, `ExtractedQuestionCandidate` DTOs |
| **Assessment & Test Engine** | `@assessment-engineer` | `documents`, `document_pages`, `topics`, `concepts`, `facts`, `LLMProvider` | `exam_configs`, `questions`, `question_options`, `tests`, `test_questions`, `attempts`, `responses` | `TestBuilderService`, `ScoringResultService`, post-submit hook |
| **Performance & Coaching** | `@performance-engineer` | `attempts`, `responses`, `test_questions`, `topics`, `notes`, `LLMProvider` | `topic_performance`, `topic_performance_snapshots`, `attempt_error_classifications`, `improvement_plans`, `revision_schedule_items` | `TopicAggregator`, `RulePlanner`, `TargetedPracticeService` |
| **Web Frontend** | `@frontend-engineer` | Backend REST `/api/v1/*` | UI state, `sessionStorage` draft recovery | Next.js App Router UI (`frontend/`) |
| **QA & Verification** | `@qa-verifier` | Entire codebase | `backend/tests/conftest.py`, `fixtures/`, `integration/`, `security/`, `e2e/` | Verification reports, test gates |

---

## 4. Database Schema Proposal (PostgreSQL + Dialect-Agnostic SQLAlchemy 2)

Core tables from `PRODUCT.md` §7.1 plus coordinator-approved extensions:

1. **`users`**: `id (PK)`, `email (unique, nullable)`, `display_name`, `created_at`.
2. **`exam_configs`**: `id (PK)`, `exam_code (unique)`, `name`, `version`, `config_json`, `source_url`, `effective_from`, `effective_to`, `created_at`.
3. **`documents`**: `id (PK)`, `user_id (FK)`, `title`, `original_filename`, `source_type (pdf|image|plain_text)`, `mime_type`, `file_size_bytes`, `sha256`, `storage_key`, `exam_config_id (FK, nullable)`, `subject_code`, `detected_subject_code`, `classification_confidence`, `chapter_or_topic_hint`, `material_type`, `language`, `source_label`, `page_count`, `status`, `extraction_version`, `coverage_summary_json`, `created_at`, `updated_at`, `deleted_at (nullable)`. Partial/active index on `(user_id, sha256)`.
4. **`document_pages`**: `id (PK)`, `document_id (FK cascade)`, `page_number`, `extracted_text`, `extraction_method`, `confidence`, `processing_status`, `needs_ocr (bool)`, `ocr_provider`, `raw_char_count`, `image_count`, `table_count`, `tables_json`, `content_hash`, `warning (nullable)`. Unique `(document_id, page_number)`.
5. **`document_chunks`**: `id (PK)`, `document_id (FK cascade)`, `chunk_index`, `page_start`, `page_end`, `section_title`, `chunk_type`, `content_text`, `asset_ids_json`, `subject_hint`, `topic_hint`, `extraction_version`, `token_estimate`, `created_at`.
6. **`document_assets`**: `id (PK)`, `document_id (FK cascade)`, `page_number`, `asset_type`, `storage_key`, `mime_type`, `width`, `height`, `bbox_json`, `created_at`.
7. **`processing_jobs`**: `id (PK)`, `document_id (FK cascade)`, `triggered_by_user_id (FK)`, `job_type`, `status`, `current_stage`, `stage_details_json`, `processed_items`, `total_items`, `progress_percent (nullable)`, `error_code`, `error_message`, `started_at`, `finished_at`, `retry_count`.
8. **`ai_generation_runs`**: `id (PK)`, `document_id (FK nullable)`, `job_id (FK nullable)`, `stage`, `model_name`, `prompt_name`, `prompt_version`, `latency_ms`, `token_usage_json`, `validation_status`, `error_message`, `created_at`.
9. **`topics`**: `id (PK)`, `subject_code`, `exam_config_id (FK nullable)`, `parent_topic_id (FK nullable)`, `name`, `slug`, `description`, `is_canonical (bool)`, `sort_order`. Unique `(subject_code, slug)`.
10. **`concepts`**: `id (PK)`, `document_id (FK cascade)`, `topic_id (FK nullable)`, `title`, `explanation`, `difficulty`, `provenance`, `confidence`, `review_status`, `source_refs_json`, `prerequisites_json`, `related_concept_ids_json`, `canonical_hash`, `model_name`, `prompt_name`, `prompt_version`, `generation_run_id (FK nullable)`, `created_at`.
11. **`facts`**: `id (PK)`, `document_id (FK cascade)`, `topic_id (FK nullable)`, `chunk_id (FK nullable)`, `fact_type`, `content`, `provenance`, `confidence`, `source_page_number`, `supporting_excerpt`, `source_refs_json`, `canonical_hash`, `conflict_group_id (nullable)`, `is_time_sensitive (bool)`, `source_date_label`, `review_status`, `model_name`, `prompt_name`, `prompt_version`, `generation_run_id (FK nullable)`, `created_at`.
12. **`notes`**: `id (PK)`, `document_id (FK cascade)`, `topic_id (FK nullable)`, `subject_code`, `note_type (detailed|quick_revision|formula_sheet|strategy_sheet)`, `title`, `content_json`, `source_concept_ids_json`, `source_fact_ids_json`, `generation_version (int)`, `status`, `model_name`, `prompt_name`, `prompt_version`, `generation_run_id (FK nullable)`, `understood_at (nullable)`, `error_message`, `created_at`.
13. **`questions`**: `id (PK)`, `document_id (FK ON DELETE SET NULL)`, `topic_id (FK nullable)`, `concept_id (FK nullable)`, `exam_config_id (FK nullable)`, `subject_code`, `question_text`, `question_type`, `difficulty`, `origin (extracted|generated|manual)`, `source_page_number`, `supporting_excerpt`, `diagram_asset_id (FK nullable)`, `passage_group_id (nullable)`, `passage_text (nullable)`, `pyq_metadata_json`, `stem_hash`, `correct_answer_data`, `explanation`, `answer_key_provenance`, `validation_status`, `model_name`, `prompt_name`, `prompt_version`, `created_at`, `updated_at`.
14. **`question_options`**: `id (PK)`, `question_id (FK cascade)`, `option_key`, `option_text`, `display_order`. *(No `is_correct` column here.)*
15. **`tests`**: `id (PK)`, `user_id (FK)`, `title`, `exam_config_id (FK nullable)`, `subject_code (nullable)`, `source_document_ids_json`, `settings_json`, `total_questions`, `max_score (Numeric(8,2))`, `status`, `created_at`.
16. **`test_questions`**: `id (PK)`, `test_id (FK cascade)`, `question_id (FK nullable)`, `display_order`, `points (Numeric(8,2))`, `negative_points (Numeric(8,2))`, `time_limit_seconds (nullable)`, `section_code (nullable)`, `passage_group_id (nullable)`, `question_snapshot_json`.
17. **`attempts`**: `id (PK)`, `test_id (FK)`, `user_id (FK)`, `timer_mode`, `status (in_progress|submitted|timed_out_submitted)`, `current_question_index (int)`, `started_at`, `expires_at (nullable)`, `submitted_at (nullable)`, `total_duration_seconds (nullable)`, `per_question_seconds (nullable)`, `total_score (Numeric(8,2) nullable)`, `max_score (Numeric(8,2))`, `total_time_ms (bigint)`, `correct_count`, `incorrect_count`, `skipped_count`, `timed_out_count`.
18. **`responses`**: `id (PK)`, `attempt_id (FK cascade)`, `test_question_id (FK)`, `selected_answer_json (nullable)`, `is_correct (nullable)`, `graded_points (Numeric(8,2) nullable)`, `time_spent_ms (bigint)`, `shown_at`, `question_expires_at (nullable)`, `last_resumed_at (nullable)`, `visit_count (int)`, `submitted_at (nullable)`, `locked_at (nullable)`, `is_marked_for_review (bool)`, `status (unvisited|answered|skipped|timed_out)`, `confidence_self_report (nullable)`, `mistake_reason_self_report (nullable)`. Unique `(attempt_id, test_question_id)`.
19. **`topic_performance`**: `id (PK)`, `user_id (FK)`, `topic_id (FK)`, `subject_code`, `attempt_count`, `question_count`, `answered_count`, `correct_count`, `timed_out_count`, `skipped_count`, `accuracy_percent (Numeric(5,2))`, `average_time_ms`, `classification_status`, `latest_attempt_id (FK nullable)`, `previous_accuracy_percent (nullable)`, `previous_average_time_ms (nullable)`, `updated_at`. Unique `(user_id, topic_id)`.
20. **`topic_performance_snapshots`**: `id (PK)`, `user_id (FK)`, `attempt_id (FK cascade)`, `topic_id (FK)`, `question_count`, `answered_count`, `correct_count`, `timed_out_count`, `accuracy_percent (Numeric(5,2))`, `average_time_ms`, `recorded_at`. Unique `(attempt_id, topic_id)`.
21. **`attempt_error_classifications`**: `id (PK)`, `attempt_id (FK cascade)`, `response_id (FK cascade)`, `topic_id (FK nullable)`, `error_category`, `confidence_level`, `observation_text`, `possible_interpretation_text`, `evidence_json`, `created_at`.
22. **`improvement_plans`**: `id (PK)`, `user_id (FK)`, `attempt_id (FK cascade)`, `plan_version`, `rule_engine_version`, `plan_json`, `ai_coaching_status`, `coaching_text_json`, `model_name`, `prompt_name`, `prompt_version`, `created_at`.
23. **`revision_schedule_items`**: `id (PK)`, `user_id (FK)`, `topic_id (FK)`, `source_attempt_id (FK nullable)`, `reason_rule_id`, `priority`, `due_at`, `status (due|completed|dismissed)`, `completed_at (nullable)`, `created_at`.

---

## 5. REST API Contract (`/api/v1` + `/health`)

### Foundation & Dashboard
- `GET /health` — DB connectivity & version check.
- `GET /api/v1/dashboard` — Continue learning, recent uploads, active jobs, recent attempts, weak topics.
- `GET /api/v1/exam-configs`, `GET /api/v1/exam-configs/{exam_code}`, `POST /api/v1/exam-configs`
- `GET /api/v1/subjects` — Active subject adapters and strategy templates.

### Documents & Jobs (`@document-engineer`)
- `POST /api/v1/documents` — Multipart upload (PDF/JPG/PNG + metadata; `409` on SHA-256 duplicate unless `allow_duplicate=true`).
- `POST /api/v1/documents/text` — Plain-text ingestion.
- `GET /api/v1/documents`, `GET /api/v1/documents/{id}`, `PATCH /api/v1/documents/{id}`, `DELETE /api/v1/documents/{id}?cascade_derived=true`
- `GET /api/v1/documents/{id}/pages?needs_ocr_only=false`
- `GET /api/v1/documents/{id}/assets/{asset_id}` — Authenticated binary stream (private storage proxy).
- `GET /api/v1/documents/{id}/coverage` — Deterministic Coverage Audit report.
- `POST /api/v1/documents/{id}/process` (`mode`: `extract_only | full | ocr_retry`) -> `202` `ProcessingJobOut`.
- `GET /api/v1/jobs`, `GET /api/v1/jobs/{job_id}`, `POST /api/v1/jobs/{job_id}/retry`

### Knowledge & Notes (`@learning-engineer`)
- `PATCH /api/v1/documents/{id}/classification` — Override subject/material type/language.
- `GET /api/v1/documents/{id}/topics`, `GET /api/v1/topics`
- `GET /api/v1/documents/{id}/knowledge`, `PATCH /api/v1/facts/{id}`
- `POST /api/v1/documents/{id}/generate-notes` -> `202` `ProcessingJobOut`.
- `GET /api/v1/documents/{id}/notes`, `GET /api/v1/notes`, `GET /api/v1/notes/{id}`, `PATCH /api/v1/notes/{id}`
- `POST /api/v1/notes/{id}/regenerate` — Single-topic/section regeneration from DB records.
- `GET /api/v1/documents/{id}/pyq-patterns` — Sample-scoped PYQ pattern analysis with denominators.

### Questions, Tests & Attempts (`@assessment-engineer`)
- `GET /api/v1/questions`, `GET /api/v1/documents/{id}/questions`, `GET /api/v1/questions/{id}`, `POST /api/v1/questions/generate`, `POST /api/v1/questions/import`, `PATCH /api/v1/questions/{id}`, `DELETE /api/v1/questions/{id}`
- `POST /api/v1/tests/preview` — Returns matching question pool count.
- `POST /api/v1/tests`, `GET /api/v1/tests`, `GET /api/v1/tests/{id}`, `POST /api/v1/tests/{id}/start`
- `GET /api/v1/attempts`, `GET /api/v1/attempts/{id}/current`, `POST /api/v1/attempts/{id}/navigate`, `POST /api/v1/attempts/{id}/responses`, `PATCH /api/v1/attempts/{id}/responses/{response_id}/self-report`, `POST /api/v1/attempts/{id}/submit`, `GET /api/v1/attempts/{id}/results`

### Performance & Coaching (`@performance-engineer`)
- `GET /api/v1/attempts/{id}/analysis`
- `POST /api/v1/attempts/{id}/improvement-plan`, `GET /api/v1/attempts/{id}/improvement-plan`
- `GET /api/v1/performance/overview`, `GET /api/v1/performance/topics`, `GET /api/v1/performance/topics/{topic_id}/trends`
- `POST /api/v1/performance/targeted-practice`
- `GET /api/v1/performance/revisions`, `PATCH /api/v1/performance/revisions/{item_id}`

---

## 6. Agent File Ownership Matrix

- **`@coordinator`**: `README.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `docker-compose.yml`, `.gitignore`, `.env.example`, `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/core/*`, `backend/app/db/*`, `backend/app/models/*`, `backend/app/api/v1/router.py`, `backend/app/api/v1/health.py`, `backend/app/api/v1/dashboard.py`, `backend/migrations/*`.
- **`@document-engineer`**: `backend/app/api/v1/{documents.py,jobs.py}`, `backend/app/schemas/{document.py,job.py}`, `backend/app/repositories/document_repo.py`, `backend/app/services/document_ingestion/*`, `backend/app/services/extraction/*`, `backend/tests/unit/documents/*`.
- **`@learning-engineer`**: `backend/app/ai/*`, `backend/app/api/v1/{notes.py,topics.py}`, `backend/app/schemas/{notes.py,topics.py,knowledge.py}`, `backend/app/repositories/{knowledge_repo.py,notes_repo.py}`, `backend/app/services/{classification,subjects,knowledge,notes}/*`, `backend/tests/unit/learning/*`.
- **`@assessment-engineer`**: `backend/app/api/v1/{exam_configs.py,questions.py,tests.py,attempts.py}`, `backend/app/schemas/{exam_config.py,question.py,test.py,attempt.py}`, `backend/app/repositories/{exam_config_repo.py,question_repo.py,test_repo.py,attempt_repo.py}`, `backend/app/services/{question_generation,question_validation,assessment}/*`, `backend/tests/unit/assessment/*`.
- **`@performance-engineer`**: `backend/app/api/v1/performance.py`, `backend/app/schemas/performance.py`, `backend/app/repositories/performance_repo.py`, `backend/app/services/performance/*`, `backend/tests/unit/performance/*`.
- **`@frontend-engineer`**: `frontend/**` (`app/`, `components/`, `lib/`, `tests/unit/`).
- **`@qa-verifier`**: `backend/tests/{conftest.py,fixtures/**,integration/**,security/**}`, `e2e/**`, `docs/qa/**`.
