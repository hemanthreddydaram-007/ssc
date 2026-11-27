# IMPLEMENTATION_PLAN.md — AI Exam Coach

**Execution Model:** Vertical slices across Milestones M0–M8. No worker implements a milestone before `@coordinator` approves shared contracts and dispatches that milestone's task cards.

---

## Milestone Plan & Parallelisation Matrix

### M0 — Project Foundation & Shared Contracts *(Sequential Gate)*
- **Objective:** Bootable Next.js + FastAPI + PostgreSQL skeleton, Alembic baseline, logging, config, `/health`, and test harnesses.
- **Tasks:**
  - `@coordinator`: Repo hygiene (`.gitignore`, `.env.example`, `docker-compose.yml` for Postgres 16, `README.md`), `backend/pyproject.toml`, `core/` config & logging, `db/` session, initial SQLAlchemy models & Alembic `0001_initial`, `/health` endpoint.
  - `@frontend-engineer` *(parallel after repo skeleton)*: Next.js App Router + TypeScript strict + Tailwind + shadcn/ui shell, 7-item nav layout, `/settings`, health check banner.
  - `@qa-verifier`: `backend/tests/conftest.py`, `FakeLLMProvider` / `FakeOCRAdapter` harnesses, CI check scripts (`pytest`, `ruff`, `tsc --noEmit`, `lint`, `build`).
- **Acceptance Gate:** `GET /health` returns `200` with DB OK; `alembic upgrade head` passes; `tsc --noEmit`, `eslint`, and `next build` pass; `.env` not committed.

### M1 — Upload & Document Library
- **Objective:** Secure PDF/image/text ingestion, private storage, SHA-256 deduplication, library list/detail/delete.
- **Tasks (Parallel once M0 passes):**
  - `@document-engineer`: `StorageBackend` (`LocalPrivateStorage`), magic-byte/size/page validator, SHA-256 duplicate `409` handling, `/documents` & `/documents/text` CRUD + ownership checks.
  - `@frontend-engineer`: `/library` UploadDropzone, TextPasteForm, MetadataForm, DocumentTable, duplicate/error alerts.
  - `@qa-verifier`: Tests for valid PDF, spoofed MIME/extension, corrupt/encrypted PDF, oversized file, SHA-256 duplicate, private storage isolation, cross-user `403`/`404`, and delete policy.

### M2 — Document Extraction & Page Review
- **Objective:** Page-level PyMuPDF + pdfplumber extraction, scan/garbled detection, `OCRAdapter` interface, diagram assets, stage-based job status, coverage audit.
- **Tasks:**
  - `@document-engineer`: `pdf_extractor.py`, `scan_detector.py`, `ocr_adapter.py` (`NullOCRAdapter` + `GeminiVisionOCRAdapter` stub/interface), `chunker.py`, `coverage_audit.py`, `/pages`, `/assets/{asset_id}`, `/jobs/{job_id}`.
  - `@frontend-engineer`: Processing Status discrete stage checklist (no fake %), Document Workspace `Overview` (coverage audit) & `Source Pages` tab with private image proxy.
  - `@qa-verifier`: Text PDF vs. scanned/image-only PDF fixture tests, `FakeOCRAdapter` test, chunk atomicity tests (question+options & passage+questions), zero-LLM verification on `/pages`.

### M3 — AI Provider & Structured Knowledge Extraction
- **Objective:** `LLMProvider` + Gemini adapter + 1-retry Pydantic repair, subject classifier, topic/concept/fact/question-candidate extraction, deduplication & conflict flagging.
- **Tasks:**
  - `@learning-engineer`: `ai/` (`LLMProvider`, `GeminiLLMProvider`, `MockLLMProvider`, prompts), `classification/`, `knowledge/` (`extractor.py`, `deduplicator.py`, `grounding.py`), `ai_generation_runs` logging.
  - `@assessment-engineer` *(handoff from extractor)*: Consume `ExtractedQuestionCandidate` into initial PYQ extraction persistence (`questions` / `question_options`).
  - `@qa-verifier`: `FakeLLMProvider` tests for 1-retry repair & `needs_review` quarantine, provenance verification, `unknown` subject/topic support, idempotent reprocessing & conflict preservation.

### M4 — Smart Notes, Quick Revision & Solving Strategies
- **Objective:** Detailed notes, genuinely shorter quick revision, and subject-specific strategies (Maths, Reasoning, English, GA) built strictly from stored knowledge records, plus single-topic regeneration.
- **Tasks:**
  - `@learning-engineer`: `subjects/` (`maths.py`, `reasoning.py`, `english.py`, `general_awareness.py`), `notes/` (`generator.py`, `regenerator.py`, `validators.py` incl. SymPy checks), `/notes` endpoints, `/pyq-patterns`.
  - `@frontend-engineer`: Global `/notes`, `/notes/[noteId]` Notes Reader (TOC, KaTeX formulas, `Extracted` vs `AI explanation` badges, source page links, print/export, single-topic regenerate dialog).
  - `@qa-verifier`: Notes provenance & label separation tests, quick-revision conciseness test, empty-topic guard, single-topic regeneration without PDF re-extraction, Maths arithmetic check test.

### M5 — Question Bank & Validation
- **Objective:** Extracted + generated + imported question bank with strict validation, deterministic Maths solver, deduplication, and non-active review UI.
- **Tasks:**
  - `@assessment-engineer`: `question_generation/` (`generator.py`, `pyq_importer.py`, `deduplicator.py`), `question_validation/` (`validator.py`, `math_solver.py`, `option_checks.py`), `exam_config_service.py` (seeded `ssc_chsl_tier_1`), `/questions` & `/exam-configs`.
  - `@frontend-engineer`: `/question-bank` filters, QuestionDetailDrawer (outside active test), manual review/flagging, "Create Test from selection".
  - `@qa-verifier`: 4-distinct-option & single-answer tests, deterministic Maths solver rejection of wrong AI answers, duplicate stem rejection, conflicting source-key `needs_review` flagging.

### M6 — Timed Test Engine & Test Player
- **Objective:** Test builder with immutable snapshots, Speed Challenge (35s default), Exam Simulation, Learning Mode, server-authoritative timers, zero answer-key leaks, and exact `Decimal` scoring.
- **Tasks:**
  - `@assessment-engineer`: `test_builder.py`, `attempt_engine.py`, `timer_service.py` (`EXPIRY_GRACE_MS=1500`), `scoring_service.py`, `/tests` & `/attempts` endpoints (incl. `/results`).
  - `@frontend-engineer`: `/tests/new` Test Builder + `/tests/preview`, distraction-free `/attempts/[attemptId]` Test Player (server-synced countdown, refresh recovery, mobile tap targets, keyboard nav, self-report tags).
  - `@qa-verifier`: Snapshot immutability, zero answer-key leak audit across all active endpoints, Speed Challenge expiry/timeout & refresh tests, Exam Simulation total expiry auto-submit, Learning Mode single-question reveal, negative-marking `Decimal` unit tests.

### M7 — Performance Analytics & Improvement Plan
- **Objective:** Attempt analysis, speed-accuracy anomalies, evidence-based error categories, cross-attempt trends, rule-based improvement plan + grounded AI coaching, targeted practice & revision queue.
- **Tasks:**
  - `@performance-engineer`: `services/performance/*` (`metrics_calculator.py`, `error_classifier.py`, `topic_aggregator.py`, `rule_planner.py`, `ai_coach.py`, `targeted_practice.py`, `revision_scheduler.py`), `/performance/*`, `/analysis`, `/improvement-plan`.
  - `@frontend-engineer`: `/attempts/[attemptId]/results` (Results Report + Observation vs. Possible Interpretation + Improvement Plan + Revise/Targeted Practice), `/performance` dashboard charts, `/dashboard` full summary.
  - `@qa-verifier`: Hand-calculated metric verification, `<5` attempts -> `insufficient_data`, outlier latency handling, AI coaching metric-grounding & fallback tests, multi-attempt delta & targeted practice E2E.

### M8 — Quality, Usability, Security & Pilot
- **Objective:** End-to-end polish, accessibility/mobile audit, security review, and pilot validation on >=3 real SSC CHSL PDFs (including tables/diagrams).
- **Tasks:** All workers fix defects within owned modules; `@qa-verifier` runs full Playwright E2E suite (`Upload -> Notes -> 35s Speed Challenge -> Results -> Improvement Plan -> Retest`), security audit, and manual SSC CHSL pilot spot-check.
