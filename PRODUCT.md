# PRODUCT.md — AI Exam Coach

**Source of truth for product requirements and implementation.**

**Working title:** AI Exam Coach  
**Build environment:** Google Antigravity  
**Recommended first release:** SSC CHSL Tier 1, with a subject-agnostic core architecture  
**Document purpose:** A build-ready product specification for planning and implementing the MVP in small, verifiable stages.

---

## 0. Executive summary

AI Exam Coach turns a student's own study material into a connected learning and assessment system.

The student uploads a PDF, previous-year paper, question bank, notes, or other supported study material. The application analyses it, extracts concepts and questions, and generates:

1. Detailed smart notes.
2. Quick-revision notes.
3. Formulas, rules, shortcuts, and solving strategies where suitable.
4. Topic-wise practice questions.
5. Timed tests and exam simulations.
6. A performance report identifying strengths, weak topics, speed issues, and suggested next steps.
7. Targeted notes and practice generated from the student's weak areas.

The central product loop is:

**Upload → Understand → Learn → Practise → Test → Analyse → Improve → Retest**

The product should not be a generic PDF summariser. Its main differentiator is the connection between source-grounded study material, timed performance data, and personalised follow-up practice.

### Product principle

Every generated note, fact, question, answer, and recommendation should retain provenance wherever possible: which uploaded document and page supports it, whether it was extracted or generated as an explanation, and how confident the system is in it.

### Important scope decision

Design the core engine to support many subjects and examinations, but do not try to perfect every exam in version one. Use **SSC CHSL Tier 1** as the first configured exam pack because it gives the MVP four clear subject areas:

- Quantitative Aptitude / Maths
- General Intelligence / Reasoning
- English Language
- General Awareness

The architecture should allow additional exam packs and college subjects later through configuration, not by rewriting the core application.

---

# 1. Product definition

## 1.1 Problem being solved

Students commonly have PDFs, textbooks, previous-year papers, coaching notes, and question banks, but they still have to do several jobs manually:

- Find the important concepts inside large documents.
- Convert material into understandable notes.
- Prepare short revision sheets.
- Identify shortcuts and efficient solving methods.
- Create practice tests from the uploaded content.
- Track speed and accuracy.
- Understand why they are getting questions wrong.
- Decide what to study next.

AI Exam Coach should reduce this fragmented work by using one shared content and performance system.

## 1.2 Target users

### Primary MVP user
A student preparing for SSC CHSL Tier 1 who has PDFs, coaching material, and previous-year question papers.

### Later users
- SSC CGL, MTS, CPO and other SSC candidates.
- Banking and railway exam candidates.
- Students studying school, diploma, and university subjects.
- Teachers or tutors preparing topic-wise tests from their own material.

## 1.3 Core product modules

| Module | Purpose | MVP status |
|---|---|---|
| Document Library | Upload and organise learning material | Must have |
| Document Intelligence | Extract, classify, and structure content | Must have |
| Smart Notes | Generate detailed notes | Must have |
| Quick Revision | Generate compact revision material | Must have |
| Solving Strategies | Subject-specific tricks and methods | Must have, but clearly label limitations |
| Question Bank | Extract and generate questions | Must have |
| Timed Test Engine | Run per-question and full-test timers | Must have |
| Performance Analytics | Score, accuracy, speed, and topic analysis | Must have |
| Improvement Planner | Convert weak areas into a study plan | Must have, basic rules first |
| Adaptive Practice | Adjust difficulty and question mix | Later enhancement |
| Spaced Revision | Schedule review of weak or forgotten content | Later enhancement |
| Multi-user / Teacher workspace | Shared classes and assignments | Out of MVP |

## 1.4 Product non-goals for the first release

Do not build these initially:

- A fully autonomous multi-agent swarm.
- A general-purpose chatbot that answers anything without document context.
- A full social network or student community.
- Payments, subscriptions, or a marketplace.
- Live classes or video lessons.
- Native Android/iOS apps.
- Automatic scraping of coaching websites.
- Claims that the AI can predict future exam questions.

These add complexity without proving the core product value.

---

# 2. Product experience and user journeys

## 2.1 Journey A — Create study material from a document

1. Student opens the dashboard.
2. Selects **Upload Material**.
3. Uploads a PDF, image, or supported document.
4. Enters or confirms:
   - Exam (for example, SSC CHSL Tier 1).
   - Subject (Maths, Reasoning, English, General Awareness, or Auto-detect).
   - Chapter/topic if known.
   - Material type (notes, textbook, previous-year paper, question bank, current-affairs PDF, or other).
   - Language.
5. System validates the file and creates a processing job.
6. Student sees processing stages and can leave the page.
7. System produces a document report:
   - Pages processed.
   - Pages that could not be read.
   - Questions detected.
   - Topics detected.
   - Duplicate or low-confidence content.
8. Student opens the generated workspace.
9. Student selects one of:
   - Detailed Notes.
   - Quick Revision.
   - Formulas / Rules / Shortcuts.
   - Topic-wise Questions.
   - Source Review.
10. Student can regenerate one topic without processing the entire document again.

## 2.2 Journey B — Create a test from uploaded material

1. Student opens the document or a question bank.
2. Selects **Create Test**.
3. Chooses:
   - Test name.
   - Number of questions.
   - Topic or full document.
   - Difficulty mix.
   - Question source: extracted questions, AI-generated questions, or mixed.
   - Timer mode.
   - Negative marking, if applicable.
   - Whether explanations appear after each question or only after submission.
4. Preview screen shows question count and settings.
5. Student starts the test.
6. Test player records answers, time spent, skips, and timeouts.
7. Student submits or the test ends automatically.
8. Results show score, accuracy, speed, topic performance, skipped questions, and explanations.
9. Student opens the AI improvement plan.
10. Student starts targeted practice generated from weak topics.

## 2.3 Journey C — Improve a weak topic

1. Student opens the result report.
2. Selects a weak topic, for example **Time and Work**.
3. System shows:
   - Questions attempted in this topic.
   - Correct and incorrect answers.
   - Average time.
   - Repeated error patterns, when enough evidence exists.
   - Supporting source pages.
4. Student chooses **Revise this topic**.
5. System opens the relevant smart notes and worked examples.
6. Student practises easier questions first, then medium and timed questions.
7. A new mini-test checks whether performance improved.
8. System compares the new attempt with the earlier attempt.

## 2.4 Journey D — Teacher / tutor use (future)

A teacher uploads their own notes or question bank, chooses a class and topic, creates an assignment, and views class-level results. Do not implement this until the single-student workflow works reliably.

---

# 3. Feature 1 — Intelligent Study Material Generator

## 3.1 Input types

MVP priority:

1. Text-based PDF.
2. Scanned PDF with OCR fallback.
3. Image files (JPG / PNG) for individual questions or pages.
4. Plain text pasted by the user.

Later:

- DOCX.
- PPTX.
- XLSX tables.
- EPUB and web links, subject to rights and reliability.

### Upload metadata

Ask the user for as little as possible. Auto-detect when confidence is high, but let the user correct it.

- Document title.
- Exam / course.
- Subject.
- Chapter or topic (optional).
- Material type.
- Language.
- Source / publisher label (optional, for the student's own organisation).

Do not assume that an uploaded document is accurate simply because it came from a coaching brand.

## 3.2 Generated outputs

### A. Detailed smart notes

Each topic should contain:

1. Topic title and learning objective.
2. Simple definition or concept explanation.
3. Why the concept matters.
4. Step-by-step explanation.
5. Worked examples.
6. Important facts, formulas, rules, or dates.
7. Common misconceptions and traps.
8. Representative questions.
9. Exam relevance, only when supported by supplied PYQs or a configured exam syllabus.
10. Source references to the uploaded material.

### B. Quick-revision notes

Should be genuinely shorter than detailed notes:

- Key facts.
- Formula / rule sheet.
- Definitions.
- Important comparisons.
- Mnemonics only when useful and accurate.
- Frequently confused points.
- A final 1-minute recap.

### C. Subject-specific solving strategies

The AI must identify the subject and use a specialised output template.

**Maths / Quantitative Aptitude**
- Standard method.
- Alternative method, where valid.
- Faster method or shortcut, where mathematically justified.
- Formula and assumptions.
- One worked example.
- When the shortcut is safe to use.
- Common calculation errors.
- Approximate time comparison only if measured or clearly labelled as an estimate.

**Reasoning**
- Pattern or relationship being tested.
- Reliable solving procedure.
- Diagram / table / notation where it helps.
- Faster recognition cues.
- Cases where a shortcut fails.
- Worked examples.

**English**
- Exact grammar rule.
- Correct and incorrect examples.
- Vocabulary with meaning and usage.
- Elimination logic, if applicable.
- Common traps.
- Practice items that test the same rule in new contexts.

**General Awareness / Current Affairs**
- Who / what / when / where / why.
- Ministry, organisation, location, date and beneficiary fields where applicable.
- Short factual tables.
- Timeline or event sequence when useful.
- Separate current facts from static background facts.
- Flag facts whose correctness may have changed since the source was published.

**Science**
- Concept explanation.
- Formula / equation / unit.
- Labelled diagram description or generated diagram specification.
- Worked numericals.
- Common confusions.

**College / theory subjects**
- Learning objectives.
- Definitions.
- Concept hierarchy.
- Step-by-step explanation.
- Algorithms / derivations / diagrams as appropriate.
- Exam-style long and short answers if the user selects that mode.

### D. PYQ pattern analysis

When the student uploads multiple previous-year papers, the system should identify:

- Questions by subject and topic.
- Repeated concepts.
- Repeated question templates.
- Topic frequency in the uploaded sample.
- Difficulty distribution.
- Years / shifts represented.

Every statistical claim must show its denominator, e.g. "Topic X appeared in 8 of the 120 questions detected across 4 uploaded papers." Do not convert a small or biased sample into an official exam-weightage claim.

## 3.3 Source-grounding rules

Every generated item should have a source status:

- **Extracted:** directly found in the uploaded material.
- **Paraphrased:** rewritten from the uploaded material without changing meaning.
- **AI explanation:** additional explanation generated to help understanding.
- **Externally verified:** checked against an allowed authoritative external source (not part of the MVP unless web verification is explicitly enabled).
- **Unverified:** uncertain, incomplete, or not supported well enough.

The UI must not present AI explanations as direct quotations or source facts.

---

# 4. Feature 2 — Timed Examination and Performance Coach

## 4.1 Test creation settings

Required fields:

- Test title.
- Source document / question bank.
- Subject and topics.
- Question count.
- Question selection mode: extracted, generated, or mixed.
- Difficulty distribution: easy / medium / hard.
- Timer mode.
- Negative marking configuration.
- Shuffle questions and options (optional).
- Explanations after each question or after final submission.

## 4.2 Timer modes

Do not enforce one universal 35-second limit. A fixed per-question limit is useful for speed practice, but different question types require different amounts of time.

Provide three modes:

### Mode 1 — Speed Challenge
- Default preset: 35 seconds per question.
- User can choose 15 / 25 / 35 / 45 / 60 seconds or custom time.
- At timeout, record the question as timed out / unanswered.
- Optionally move automatically to the next question.
- The countdown displayed by the browser is only a visual aid; the backend timestamp is authoritative.

### Mode 2 — Exam Simulation
- Total exam duration, not a fixed per-question cap.
- Configurable sections and question counts.
- Support negative marking.
- Track time spent on each question.
- Allow navigation, review, skip and return according to exam configuration.
- Later, create official exam presets only after verifying the current exam notification.

### Mode 3 — Learning Mode
- No countdown.
- Hints can be enabled or disabled.
- Explanation appears after submission.
- Student can review the full solution.

## 4.3 Test player behaviour

Required:

- One question at a time by default.
- Clear question number and total count.
- Countdown / remaining test time.
- Answer selection.
- Next / previous navigation when mode permits.
- Mark for review.
- Save answer state.
- Submission confirmation.
- Auto-submit on total duration expiry.
- Auto-record a per-question timeout in Speed Challenge.
- Handle refresh or connection interruption without losing committed answers.
- Keyboard navigation where practical.
- Accessible controls and visible focus states.

### Timing correctness

Do not trust a client-side JavaScript timer as the only source of truth.

When an attempt starts, the backend stores `started_at` and the configured expiry information. For a per-question timer, the backend stores the question's `shown_at` / `expires_at`. On answer submission, the server checks whether the response arrived before expiry. The frontend countdown is derived from the server time and may be re-synchronised after refresh.

For the MVP, a server timestamp check is sufficient. Do not build complex anti-cheat or proctoring systems.

## 4.4 Results report

Show:

- Total score.
- Correct / incorrect / skipped / timed-out counts.
- Accuracy.
- Average time per attempted question.
- Topic-wise accuracy.
- Topic-wise average time.
- Difficulty-wise performance.
- Questions where the student spent unusually long.
- Questions answered too quickly and incorrectly, as a possible guess / reading issue signal.
- Review of all questions with correct answers and explanations.

### Important: distinguish observation from diagnosis

The system can observe that a student answered incorrectly in 12 seconds. It cannot know with certainty that the student was careless.

Use wording such as:

- Observation: "You answered 4 questions incorrectly in under 10 seconds."
- Possible interpretation: "This may indicate rushed reading or guessing."
- Recommendation: "Try a short accuracy-first drill and compare results."

Do not state a psychological or learning diagnosis as fact based only on answer data.

## 4.5 Error categories

Use the following as tentative classifications:

1. Concept gap.
2. Rule / formula recall issue.
3. Calculation error.
4. Reading / interpretation issue.
5. Method selection issue.
6. Time pressure / timeout.
7. Guess / low-confidence attempt.
8. Question not attempted.
9. Answer-key / source ambiguity.

Allow the student to optionally mark "I guessed", "I knew the method but made a mistake", or "I did not understand the concept" after a question. This improves diagnosis.

## 4.6 Personalised improvement plan

The first version should use transparent rules rather than relying entirely on another AI opinion.

Example rule logic:

- Topic accuracy below 50% and at least 5 attempts → recommend concept revision.
- Accuracy 50–75% → recommend worked examples and medium practice.
- Accuracy above 75% but average time is high → recommend speed drills.
- Many timeouts → recommend shorter timed sets and question-selection practice.
- Fewer than 5 attempts in a topic → mark "insufficient data" rather than assigning a firm weakness.

AI can convert these signals into clear natural-language coaching. It must not fabricate evidence.

---

# 5. Shared AI intelligence and document-processing pipeline

This is the technical heart of the product.

## 5.1 Pipeline overview

```text
Upload file
   |
   v
Validate file and create document record
   |
   v
Extract pages, text, tables, images and page numbers
   |
   +----> OCR / visual processing fallback for scanned pages
   |
   v
Create page-level structured content
   |
   v
Classify subject, chapter, concepts and question types
   |
   v
Extract facts, formulas, rules, examples and questions
   |
   v
Validate and deduplicate structured records
   |
   +----------------------------+
   |                            |
   v                            v
Generate detailed notes       Build question bank
   |                            |
   v                            v
Generate quick revision       Validate answers/options
   |                            |
   v                            v
Generate solving methods      Build tests
   |                            |
   +--------------+-------------+
                  |
                  v
          Shared knowledge base
                  |
                  v
       Student attempts timed tests
                  |
                  v
        Performance analytics
                  |
                  v
      Personalised improvement plan
                  |
                  v
       Targeted notes and practice
```

## 5.2 File ingestion

### Validation

- Accept only configured MIME types and extensions.
- Verify actual file signature; do not trust extension alone.
- Set a maximum file size and page count for the MVP.
- Reject corrupt, encrypted, password-protected, or unsupported files with a clear message.
- Store uploaded files outside the public web root.
- Generate a SHA-256 hash to detect duplicate uploads.
- Never execute content embedded in documents.

### Extraction strategy

Use a hybrid approach:

1. Try local text extraction for selectable-text PDFs.
2. Preserve page boundaries and page numbers.
3. Extract tables where possible.
4. Detect pages with very little text or likely scans.
5. Use OCR or a multimodal vision model for those pages.
6. Preserve images / diagrams for visual questions.
7. Store extraction confidence and warnings.

Do not send an entire very large PDF in a single prompt and assume the model will capture everything. Process in page or section chunks, maintain page references, and run a coverage check.

A multimodal Gemini API call can accept PDFs, and Gemini structured outputs can constrain results to a JSON schema. Use these capabilities selectively; local extraction first can reduce repeated model processing and cost. Check current model limits and pricing before deployment.

## 5.3 Chunking strategy

Chunk by semantic boundaries where possible:

- Chapter / section headings.
- Page ranges.
- Question groups.
- Table boundaries.
- Passage + its associated questions.

Each chunk must retain:

- Document ID.
- Page start and end.
- Section title.
- Subject and topic candidates.
- Extraction version.
- Text / image references.

Do not split a question from its options or a reading passage from the questions that refer to it.

## 5.4 Canonical knowledge records

Create structured records instead of keeping all model output as free text.

### Fact record

- Fact text.
- Subject / topic.
- Fact type (date, person, place, formula, definition, event, rule, statistic, etc.).
- Source document and page.
- Supporting excerpt.
- Provenance status.
- Confidence.
- Last verified / source date if relevant.

### Concept record

- Concept title.
- Explanation.
- Subject / topic.
- Prerequisites.
- Related concepts.
- Source references.

### Question record

- Stem.
- Question type.
- Options.
- Correct answer.
- Explanation.
- Subject / topic.
- Difficulty.
- Source document / page when extracted.
- Whether it is extracted or AI-generated.
- Answer-key provenance.
- Validation status.

### Note record

- Note type (detailed, quick revision, formula sheet, shortcut sheet).
- Topic / concept links.
- Sections / content blocks.
- Source references.
- Generation version.
- Review status.

## 5.5 AI processing stages

Use a controlled pipeline. These can be logical AI modules; they do not need to be separate autonomous agents.

| Stage | Input | Output | Validation |
|---|---|---|---|
| Document classifier | Page/chunk content | Subject, material type, language | User can correct classification |
| Content extractor | Page/chunk | Facts, concepts, formulas, questions | Page citations required |
| Topic mapper | Extracted records + exam config | Topic and chapter assignment | Unknown topic allowed |
| Deduplicator | Structured records | Merged / linked duplicates | Never merge facts with conflicting values |
| Notes generator | Validated facts and concepts | Detailed and quick notes | Check every source reference |
| Strategy generator | Concepts + example questions | Methods and shortcuts | Validate mathematical / logical correctness |
| Question generator | Concepts / facts / target difficulty | MCQs and other formats | One valid answer; plausible distractors |
| Answer validator | Question + options + source | Verified / needs review | Deterministic checks where possible |
| Performance coach | Attempt data + thresholds | Improvement plan | Recommendations must cite actual metrics |

## 5.6 AI output requirements

Every AI stage should return schema-conforming JSON, not arbitrary prose that later code tries to parse.

Use Pydantic models to validate the response. If a model returns invalid JSON or missing fields:

1. Retry with a repair prompt once.
2. If it remains invalid, mark the item as failed review.
3. Do not silently accept malformed records.

Suggested generic source reference shape:

```json
{
  "document_id": "uuid",
  "page_number": 12,
  "section_title": "Percentages",
  "supporting_excerpt": "...",
  "provenance": "extracted"
}
```

Suggested question shape:

```json
{
  "question_text": "...",
  "question_type": "single_choice",
  "subject": "maths",
  "topic": "percentages",
  "difficulty": "medium",
  "options": [
    {"key": "A", "text": "..."},
    {"key": "B", "text": "..."},
    {"key": "C", "text": "..."},
    {"key": "D", "text": "..."}
  ],
  "correct_option_key": "B",
  "explanation": "...",
  "source_refs": [
    {"document_id": "uuid", "page_number": 12}
  ],
  "answer_key_provenance": "source_answer_key",
  "validation_status": "verified"
}
```

The example is a schema illustration only. The actual implementation should define Pydantic models and enums.

## 5.7 Question quality checks

A generated question should not enter the normal question bank until it passes checks:

- The stem is complete and unambiguous.
- Exactly one option is correct for a single-answer question.
- Every distractor is distinct and clearly incorrect.
- The answer is supported by source material or a validated solver.
- Units, dates, names, and quantities are preserved correctly.
- The explanation matches the answer.
- No source page is falsely cited.
- No duplicate or near-duplicate exists in the same question set.

For Maths, use deterministic Python calculations where possible to verify the answer. For reasoning, use domain-specific validators when feasible. For English, use grammar rules and curated evaluation checks; ambiguous cases should be flagged. For Current Affairs / GK, rely on source evidence and mark conflicting or outdated facts for review.

## 5.8 Coverage audit

The product should make a best effort to avoid missing important information.

At minimum, report:

- Total pages.
- Pages successfully extracted.
- Pages requiring OCR or visual fallback.
- Pages not processed.
- Number of facts extracted.
- Number of questions extracted.
- Number of concepts identified.
- Number of records rejected or marked uncertain.
- Topics with low extraction confidence.

Do not claim "100% coverage" simply because an AI says it has read the document.

---

# 6. Subject and exam configuration system

Separate the reusable engine from exam-specific settings.

## 6.1 Exam configuration

Example configuration for SSC CHSL Tier 1 (verify the latest notification before publishing official timings or marking rules):

```json
{
  "exam_code": "ssc_chsl_tier_1",
  "display_name": "SSC CHSL Tier 1",
  "subjects": [
    "quantitative_aptitude",
    "reasoning",
    "english",
    "general_awareness"
  ],
  "question_types": ["single_choice"],
  "supports_negative_marking": true,
  "timing_mode": ["speed_challenge", "exam_simulation", "learning_mode"]
}
```

Keep official exam values in versioned configuration records and include the notification year / source link. Do not hardcode a marking scheme that may change.

## 6.2 Subject adapters

Each subject adapter defines:

- Topic taxonomy.
- Note structure.
- Relevant question types.
- Difficulty indicators.
- Solving strategy templates.
- Validation rules.
- Common misconception categories.

Initial adapters:

1. Maths.
2. Reasoning.
3. English.
4. General Awareness.

Later adapters:

- Physics, Chemistry, Biology.
- Computer Science and engineering subjects.
- Commerce and economics.
- Other exam-specific subjects.

---

# 7. Data model and database design

Use PostgreSQL for the deployable version. SQLite can be used for a very early local prototype, but the application should use SQLAlchemy models and migrations so the database can be changed cleanly.

## 7.1 Core entities

### `users`
- `id` UUID primary key.
- `email` unique, nullable during local single-user development.
- `display_name`.
- `created_at`.

### `exam_configs`
- `id` UUID.
- `exam_code` unique.
- `name`.
- `version`.
- `config_json`.
- `source_url` / official notification reference.
- `effective_from` / `effective_to`.

### `documents`
- `id` UUID.
- `user_id`.
- `title`.
- `original_filename`.
- `mime_type`.
- `file_size_bytes`.
- `sha256`.
- `storage_key`.
- `exam_config_id` nullable.
- `subject_code` nullable.
- `material_type`.
- `language`.
- `page_count`.
- `status`.
- `created_at`.

### `document_pages`
- `id` UUID.
- `document_id`.
- `page_number`.
- `extracted_text`.
- `extraction_method`.
- `confidence`.
- `processing_status`.
- `warning` nullable.

### `processing_jobs`
- `id` UUID.
- `document_id`.
- `job_type`.
- `status`.
- `progress_percent`.
- `current_stage`.
- `error_code` nullable.
- `error_message` nullable.
- `started_at` / `finished_at`.
- `retry_count`.

### `topics`
- `id` UUID.
- `subject_code`.
- `parent_topic_id` nullable.
- `name`.
- `slug`.
- `description` nullable.

### `concepts`
- `id` UUID.
- `document_id`.
- `topic_id` nullable.
- `title`.
- `explanation`.
- `difficulty` nullable.
- `created_at`.

### `facts`
- `id` UUID.
- `document_id`.
- `topic_id` nullable.
- `fact_type`.
- `content`.
- `provenance`.
- `confidence`.
- `source_page_number` nullable.
- `supporting_excerpt` nullable.
- `review_status`.

### `notes`
- `id` UUID.
- `document_id`.
- `topic_id` nullable.
- `note_type` (`detailed`, `quick_revision`, `formula_sheet`, `strategy_sheet`).
- `title`.
- `content_json`.
- `generation_version`.
- `status`.
- `created_at`.

### `questions`
- `id` UUID.
- `document_id` nullable.
- `topic_id` nullable.
- `subject_code`.
- `question_text`.
- `question_type`.
- `difficulty`.
- `origin` (`extracted`, `generated`, `manual`).
- `source_page_number` nullable.
- `correct_answer_data` stored separately from public question data.
- `explanation`.
- `answer_key_provenance`.
- `validation_status`.
- `created_at`.

### `question_options`
- `id` UUID.
- `question_id`.
- `option_key`.
- `option_text`.
- `display_order`.

### `tests`
- `id` UUID.
- `user_id`.
- `title`.
- `exam_config_id` nullable.
- `subject_code` nullable.
- `settings_json`.
- `status`.
- `created_at`.

### `test_questions`
- `id` UUID.
- `test_id`.
- `question_id`.
- `display_order`.
- `points`.
- `time_limit_seconds` nullable.
- `question_snapshot_json`.

Store a snapshot so a later edit to a question does not change an already-created test.

### `attempts`
- `id` UUID.
- `test_id`.
- `user_id`.
- `status`.
- `started_at`.
- `submitted_at` nullable.
- `total_score` nullable.
- `correct_count`.
- `incorrect_count`.
- `skipped_count`.
- `timed_out_count`.

### `responses`
- `id` UUID.
- `attempt_id`.
- `test_question_id`.
- `selected_answer_json` nullable.
- `is_correct` nullable until graded.
- `time_spent_ms`.
- `shown_at`.
- `submitted_at` nullable.
- `status` (`answered`, `skipped`, `timed_out`).
- `confidence_self_report` nullable.
- `mistake_reason_self_report` nullable.

### `topic_performance`
- `id` UUID.
- `user_id`.
- `topic_id`.
- `attempt_count`.
- `question_count`.
- `correct_count`.
- `accuracy_percent`.
- `average_time_ms`.
- `updated_at`.

### `improvement_plans`
- `id` UUID.
- `user_id`.
- `attempt_id`.
- `plan_json`.
- `created_at`.

## 7.2 Important relationships

```text
User
 ├── Documents
 │    ├── Document Pages
 │    ├── Processing Jobs
 │    ├── Facts
 │    ├── Concepts
 │    ├── Notes
 │    └── Questions
 │
 ├── Tests
 │    ├── Test Questions ── Questions
 │    └── Attempts
 │         └── Responses
 │
 ├── Topic Performance
 └── Improvement Plans
```

## 7.3 Data integrity rules

- Every extracted fact should reference a document and page when available.
- Every extracted question should retain original page / source information.
- Generated content should record its model and prompt version.
- An answer key should never be sent to the test-player API before grading.
- Test attempts should use question snapshots.
- Duplicate file uploads should be detected using SHA-256.
- Deleting a document should follow an explicit retention policy for generated records.

---

# 8. Backend API design

Use REST endpoints for the MVP. Keep route names predictable and version them under `/api/v1`.

## 8.1 Documents

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/documents` | Upload a document |
| GET | `/api/v1/documents` | List user's documents |
| GET | `/api/v1/documents/{id}` | Document details and status |
| DELETE | `/api/v1/documents/{id}` | Delete document and related data as configured |
| GET | `/api/v1/documents/{id}/pages` | Page extraction review |
| POST | `/api/v1/documents/{id}/process` | Start / retry processing |
| GET | `/api/v1/jobs/{job_id}` | Processing status |

## 8.2 Study material

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/documents/{id}/generate-notes` | Generate detailed / revision notes |
| GET | `/api/v1/documents/{id}/notes` | List notes |
| GET | `/api/v1/notes/{id}` | Read one note |
| POST | `/api/v1/notes/{id}/regenerate` | Regenerate selected topic / section |
| GET | `/api/v1/documents/{id}/topics` | List detected topics |
| GET | `/api/v1/documents/{id}/questions` | List extracted / generated questions |

## 8.3 Tests

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/tests` | Create a test |
| GET | `/api/v1/tests` | List tests |
| GET | `/api/v1/tests/{id}` | Test settings / metadata |
| POST | `/api/v1/tests/{id}/start` | Start an attempt |
| GET | `/api/v1/attempts/{id}/current` | Get current question and server-derived remaining time |
| POST | `/api/v1/attempts/{id}/responses` | Save an answer / skip |
| POST | `/api/v1/attempts/{id}/submit` | Submit attempt |
| GET | `/api/v1/attempts/{id}/results` | Results and explanations |
| GET | `/api/v1/attempts/{id}/analysis` | Topic and timing analysis |
| POST | `/api/v1/attempts/{id}/improvement-plan` | Generate improvement recommendations |

## 8.4 Validation and security

- Validate all request and response bodies with Pydantic.
- Enforce file size, MIME, page-count, and ownership checks.
- Do not accept a user-supplied correct answer as verified without marking its provenance.
- Never expose answer keys during an active test.
- Rate-limit expensive AI generation endpoints.
- Keep API keys only on the server.
- Log job IDs and errors without logging secrets or full sensitive document contents.

---

# 9. Frontend information architecture and UI

Use a desktop-first responsive web UI, but ensure the test player works well on mobile.

## 9.1 Main navigation

1. Dashboard.
2. My Library.
3. Smart Notes.
4. Question Bank.
5. Tests.
6. Performance.
7. Settings.

## 9.2 Required screens

### Screen 1 — Dashboard

Show:
- Continue learning.
- Recent uploads.
- Processing jobs.
- Recent tests.
- Study streak / activity (optional, not a launch blocker).
- Weak topics to revise.
- Quick actions: Upload Material, Generate Notes, Create Test.

### Screen 2 — Upload Material

Components:
- Drag-and-drop upload.
- File picker.
- Supported format and size text.
- Exam selector.
- Subject selector.
- Material-type selector.
- Optional chapter / topic.
- Upload progress and validation errors.

### Screen 3 — Processing Status

Show stages such as:
- File validation.
- Page extraction.
- OCR / visual review.
- Topic classification.
- Question extraction.
- Notes / question generation.
- Quality checks.

If one stage fails, show a specific retry action. Do not display fake progress percentages.

### Screen 4 — Document Workspace

Tabs:
- Overview.
- Detailed Notes.
- Quick Revision.
- Formula / Rules / Shortcuts.
- Questions.
- Source Pages.

Show coverage report and low-confidence pages.

### Screen 5 — Notes Reader

Requirements:
- Table of contents.
- Clear heading hierarchy.
- Formula and example blocks.
- Source page links.
- Copy / export / print actions.
- Regenerate selected topic.
- Mark section as understood (optional).

### Screen 6 — Question Bank

Filters:
- Subject.
- Topic.
- Difficulty.
- Source (uploaded / generated / manual).
- Validation status.

Question detail should show source information and answer explanation outside the active-test context.

### Screen 7 — Test Builder

Settings:
- Source document / question bank.
- Subject / topic.
- Question count.
- Difficulty mix.
- Extracted / generated / mixed questions.
- Speed Challenge / Exam Simulation / Learning Mode.
- Time setting.
- Negative marking.
- Preview.

### Screen 8 — Test Player

Keep the interface distraction-free:
- Question and options.
- Timer.
- Question count.
- Answer state.
- Next / previous / skip / review as mode allows.
- Submit confirmation.
- Connection / save status.

Do not show the correct answer or explanation during a normal test.

### Screen 9 — Results

Show:
- Score.
- Accuracy.
- Correct / incorrect / skipped / timed out.
- Average time.
- Topic breakdown.
- Question review.
- Improvement plan.
- Start targeted practice.

### Screen 10 — Performance Dashboard

Show changes across attempts, not just one test:
- Accuracy by topic over time.
- Average time by topic over time.
- Strong topics.
- Topics needing practice.
- Insufficient-data topics.
- Improvement since previous attempt.

---

# 10. Recommended technology stack

Use a stack that is productive in Antigravity and easy to test locally.

| Layer | Recommended choice | Reason |
|---|---|---|
| Frontend | Next.js App Router + TypeScript | Reusable UI and type safety |
| UI | Tailwind CSS + shadcn/ui | Fast, consistent components |
| Backend | Python + FastAPI | Strong fit for document and AI processing |
| Validation | Pydantic | Shared structured schemas |
| Database | PostgreSQL | Reliable relational data and analytics |
| ORM | SQLAlchemy 2 | Explicit data layer |
| Migrations | Alembic | Versioned schema changes |
| PDF text | PyMuPDF | Fast page-level text extraction |
| PDF tables | pdfplumber | Table-oriented extraction support |
| OCR | Start with a replaceable OCR adapter | Avoid locking the app to one OCR engine |
| AI provider | Gemini API behind an interface | Multimodal document processing and structured outputs |
| File storage | Local private folder for development; object storage later | Keep file handling separate from DB |
| Background jobs | Start with a job table + simple worker; add Redis / Celery or equivalent later | Avoid unnecessary infrastructure in MVP |
| Tests | pytest + frontend tests | Protect core logic and regressions |

### Architecture note

Do not couple the whole codebase directly to one Gemini model. Create a provider interface such as `LLMProvider`, with a Gemini implementation. This allows model changes or another provider later.

Example responsibilities:

- `generate_structured_output(schema, prompt, files)`
- `generate_text(prompt, context)`
- `verify_question(question, evidence)`

Keep the provider-specific SDK code inside the adapter.

### Local development recommendation

Start with:

- Next.js frontend.
- FastAPI backend.
- PostgreSQL locally, or SQLite only for the first thin prototype.
- Local file storage.
- Gemini API key stored in backend `.env`.

Do not introduce Redis, Docker orchestration, vector databases, microservices, or multiple autonomous agents until the MVP requires them.

---

# 11. Suggested repository structure

Use a monorepo to keep the frontend and backend together.

```text
ai-exam-coach/
├── README.md
├── PRODUCT.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── .gitignore
├── .env.example
├── frontend/
│   ├── app/
│   │   ├── dashboard/
│   │   ├── library/
│   │   ├── documents/[documentId]/
│   │   ├── notes/[noteId]/
│   │   ├── question-bank/
│   │   ├── tests/
│   │   ├── tests/[testId]/
│   │   ├── attempts/[attemptId]/
│   │   └── performance/
│   ├── components/
│   │   ├── layout/
│   │   ├── documents/
│   │   ├── notes/
│   │   ├── questions/
│   │   ├── test-player/
│   │   └── analytics/
│   ├── lib/
│   └── tests/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/v1/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── document_ingestion/
│   │   │   ├── extraction/
│   │   │   ├── classification/
│   │   │   ├── notes/
│   │   │   ├── question_generation/
│   │   │   ├── question_validation/
│   │   │   ├── assessment/
│   │   │   └── performance/
│   │   ├── ai/
│   │   │   ├── provider.py
│   │   │   ├── gemini_provider.py
│   │   │   ├── prompts/
│   │   │   └── schemas/
│   │   └── workers/
│   ├── migrations/
│   ├── tests/
│   └── pyproject.toml
├── storage/                 # local private files; gitignored
└── docs/
    ├── API.md
    ├── DATA_MODEL.md
    └── AI_PIPELINE.md
```

The actual folders can be adjusted after a repository review. Do not create empty folders for every future feature on day one.

---

# 12. MVP milestones and acceptance criteria

Build in vertical slices. Each milestone should leave the app runnable and testable.

## M0 — Project foundation and product rules

**Build**
- Repository structure.
- README and environment setup.
- Frontend shell and backend health endpoint.
- Configuration and logging.
- Initial database connection.
- Pydantic conventions.
- Basic test setup.

**Acceptance criteria**
- Frontend and backend start locally using documented commands.
- `/health` returns a successful response.
- Environment variables are not committed.
- A fresh clone can follow the README to start the project.

## M1 — Upload and document library

**Build**
- Upload PDF.
- Validate file type and size.
- Store file privately.
- Create document record.
- List uploaded files.
- Show document detail and processing status.

**Acceptance criteria**
- Valid PDF uploads successfully.
- Invalid file is rejected with clear feedback.
- Duplicate file hash is detected.
- File is not served from a public static directory.
- Document survives backend restart.

## M2 — Document extraction and review

**Build**
- Page-level text extraction.
- Page numbers.
- Extraction warnings.
- OCR adapter interface for scanned pages.
- Processing job status.
- Page review UI.

**Acceptance criteria**
- A text PDF extracts page-by-page.
- A scanned / image-only PDF is detected instead of silently returning empty content.
- The UI reports pages requiring OCR or manual review.
- Extraction results can be inspected without calling the LLM again.

## M3 — Structured knowledge extraction

**Build**
- Subject / material classification.
- Topic detection.
- Extract facts, formulas, concepts, and questions.
- Store source page references.
- Pydantic schema validation.
- Deduplication and review status.

**Acceptance criteria**
- Extracted items retain document and page provenance.
- Invalid AI responses are rejected or marked for review.
- Unknown subject / topic is allowed; the system must not force a wrong classification.
- Reprocessing does not create uncontrolled duplicate rows.

## M4 — Smart notes and quick revision

**Build**
- Detailed note generation.
- Quick revision generation.
- Subject-specific templates for Maths, Reasoning, English, and General Awareness.
- Notes reader UI.
- Regenerate selected topic.

**Acceptance criteria**
- Notes are based on stored knowledge records, not a fresh untraceable summary of the whole PDF.
- Source references are visible.
- AI-generated explanatory additions are labelled separately from extracted facts.
- Notes can be regenerated without re-uploading or re-extracting the PDF.

## M5 — Question bank and validation

**Build**
- Extracted question bank.
- AI-generated question bank.
- Difficulty and topic filters.
- Answer explanations.
- Answer-key provenance.
- Validation status.

**Acceptance criteria**
- Extracted questions retain original wording and source page where possible.
- Generated MCQs have four distinct options and one verified answer for single-choice mode.
- The system flags ambiguous questions and uncertain answer keys.
- Maths answers receive deterministic checks where possible.
- Duplicate questions are identified.

## M6 — Timed test engine

**Build**
- Test builder.
- Speed Challenge with configurable per-question timer and 35-second default.
- Learning Mode.
- Basic Exam Simulation with total duration.
- Test player.
- Answer saving.
- Server-side time validation.
- Scoring and negative marking configuration.

**Acceptance criteria**
- Timeouts are recorded correctly.
- Browser refresh does not reset server-side elapsed time.
- Client cannot submit an answer after the backend expiry time.
- Answer keys are not exposed by active-test endpoints.
- Score calculation has unit tests for correct, incorrect, skipped, timed out, and negative-marking cases.

## M7 — Performance analysis and improvement plan

**Build**
- Accuracy and speed analytics.
- Topic-level report.
- Strong / weak / insufficient-data categories.
- Rule-based improvement suggestions.
- AI-generated plain-language explanation of the data.
- Targeted practice creation.

**Acceptance criteria**
- Every recommendation is linked to actual attempt data.
- Topics with too few attempts are labelled insufficient data.
- The app distinguishes observed metrics from possible causes.
- A weak topic can launch its notes and a targeted practice test.

## M8 — Quality, usability, and pilot

**Build**
- Responsive UI.
- Error handling.
- Loading / empty / error states.
- Accessibility pass.
- Basic security review.
- Pilot with real SSC CHSL PDFs and PYQs.

**Acceptance criteria**
- At least 3 different source PDFs are processed successfully, including one with tables or images.
- A small set of extracted questions is manually checked against the original.
- Generated questions are manually reviewed for answer correctness and ambiguity.
- A full test can be completed from start to results without data loss.
- Performance results match independently calculated test scores.

---

# 13. MVP success metrics

Do not measure success only by the number of notes or questions generated.

## Product reliability
- Upload success rate.
- Pages extracted successfully.
- Percentage of source records with page references.
- AI schema validation rate.
- Question validation pass rate.
- Duplicate question rate.
- Test submission / timer correctness.

## Student value
- Time from upload to usable notes.
- Percentage of notes the student opens or revises.
- Test completion rate.
- Repeat test rate.
- Accuracy improvement on new, comparable questions.
- Average solving-time improvement without a decline in accuracy.
- Number of weak topics that improve after targeted practice.

## Suggested pilot evaluation

Use a small set of known papers. Manually compare:

1. Extracted questions against the source.
2. Generated facts against the source.
3. Correct answers against a trusted answer key or independently solved result.
4. Notes for missing or distorted information.
5. Performance reports against hand-calculated metrics.

Only after this evaluation should you increase automation.

---

# 14. Reliability, privacy, safety, and copyright

## 14.1 Reliability

- Never treat a model response as verified solely because it is fluent.
- Keep evidence references for extracted facts and questions.
- Flag uncertain answer keys.
- Use deterministic solvers for arithmetic and scoring where possible.
- Keep model prompts versioned.
- Log AI model, version, input document, generation time, and validation result.
- Support manual correction of extracted content.

## 14.2 Privacy and security

- Keep uploaded documents private to the user.
- Do not use public file URLs by default.
- Protect the Gemini API key on the backend.
- Add upload limits and request rate limits.
- Validate user ownership on every document, note, test, and attempt endpoint.
- Do not log full documents or API secrets.
- Provide a delete-document action and define whether derived notes / questions are deleted with it.
- Add authentication before exposing the app publicly.

## 14.3 Copyright

Students should upload material they have the right to use. Keep their files private. Do not redistribute or publicly expose uploaded coaching PDFs, and do not build scraping or sharing features around copyrighted material without permission.

## 14.4 AI limitations shown to students

Use plain labels:

- Source-backed.
- AI explanation.
- Needs review.
- Not enough information.

If an uploaded document has a wrong answer key or outdated fact, the application should flag the conflict rather than blindly reproducing it.

---

# 15. Antigravity development workflow

Antigravity should be used as an engineering collaborator, not instructed to build the entire product in one giant prompt.

## 15.1 Before coding

1. Create a Git repository.
2. Open the project folder in Antigravity.
3. Add this blueprint as `PRODUCT.md` or keep it in `docs/`.
4. Create a separate `IMPLEMENTATION_PLAN.md`.
5. Ask Antigravity to inspect the spec and identify ambiguities, risks, and implementation dependencies.
6. Approve the architecture before implementation.

Use Antigravity's planning mode for architecture and multi-file changes. Work in small milestones and review diffs. Use isolated worktrees when parallel tasks could modify overlapping files. The current Antigravity documentation describes project boundaries, Local and New Worktree modes, plan/review workflows, and agent task execution; confirm the exact UI and available modes in the installed version.

## 15.2 Recommended Antigravity rules

Create a repository-level rules file if supported by the installed Antigravity version. Suggested project rules:

- Read `PRODUCT.md`, `ARCHITECTURE.md`, and `ROADMAP.md` before making structural changes.
- Do not implement multiple milestones in one task.
- Do not replace working architecture without explaining why.
- Do not add dependencies without justification.
- Use TypeScript strict mode.
- Use Pydantic schemas for backend request / response and AI output validation.
- Keep AI provider SDK calls inside the provider adapter.
- Never expose API keys to the frontend.
- Never return answer keys from active-test endpoints.
- Preserve document and page provenance.
- Add unit tests for business logic and API tests for endpoints.
- Run tests and type checks after every milestone.
- Do not claim a feature works unless it has been run and verified.
- Keep unfinished functionality clearly marked; do not use fake data in production paths.

## 15.3 Swarm-based Antigravity workflow

This project is intended to be built with Antigravity's development-time swarm. The swarm is a way to divide engineering work; it is **not** a feature of the student-facing application.

### Recommended team

| Worker | Owns | Must coordinate with |
|---|---|---|
| Main coordinator / architect | Product decisions, architecture, task breakdown, API contracts, integration, milestone approvals | All workers |
| Document engineer | Upload, file validation, storage adapter, PDF extraction, page-level extraction records, OCR adapter | Learning, Assessment, Frontend, QA |
| AI learning engineer | AI provider integration (with coordinator-approved interface), knowledge extraction, topic classification, notes, revision notes, subject strategy generation | Document, Assessment, QA |
| Assessment engineer | Question bank, question schemas, answer validation, test creation, timer/scoring backend | Document, Performance, Frontend, QA |
| Performance engineer | Attempt analytics, topic performance, error evidence, improvement plans, revision recommendations | Assessment, Learning, QA |
| Frontend engineer | UI routes, components, upload experience, notes reader, question bank, test player, results dashboards | All feature owners through agreed API contracts |
| QA / verifier | Independent tests, API checks, security review, end-to-end verification; should not independently redesign feature modules | All workers; reports to coordinator |

### Ownership and collision rules

1. The coordinator owns shared architecture documents, database schema decisions, migrations, environment configuration, API contract approval, and integration decisions.
2. Feature agents own their assigned service modules and tests. They must not independently edit shared database models, migrations, or common API schemas without coordinator approval.
3. The frontend agent owns frontend code only. Backend agents own backend modules. Cross-boundary work must follow a written API contract.
4. QA is a reviewer and verifier, not a second implementation owner. QA may submit focused fixes only when the coordinator explicitly assigns them.
5. No two workers should modify the same files concurrently. Use isolated worktrees or sequential handoffs when file overlap is unavoidable.
6. Every task must state: objective, scope, files allowed to change, dependencies, acceptance criteria, and tests required.
7. Workers must report blockers and contract changes on the shared swarm board before proceeding.
8. The coordinator integrates and runs the complete relevant test suite after every milestone.
9. Do not create autonomous agents inside the student-facing product. Backend AI modules should begin as ordinary services and deterministic pipeline stages.
10. Do not parallelise work until shared contracts and data ownership are agreed.

### Initial swarm planning prompt

Paste this into Antigravity after opening the repository and starting `/swarm`. This is a planning request; it must not start broad implementation.

```text
We are building AI Exam Coach. Read PRODUCT.md completely before making implementation decisions.

You are the main coordinator. Use the Antigravity development swarm to organise the engineering work. The swarm is for building the product only; do not implement a student-facing multi-agent swarm feature.

Create or assign these workers:
1. @document-engineer — upload, validation, private storage, PDF extraction, OCR fallback, page-level provenance.
2. @learning-engineer — structured knowledge extraction, subject classification, detailed notes, quick revision notes, and subject-specific solving strategies.
3. @assessment-engineer — extracted/generated question bank, question validation, test builder, timers, scoring, and answer explanations.
4. @performance-engineer — response analytics, accuracy/speed/topic metrics, evidence-based mistake categories, and improvement plans.
5. @frontend-engineer — user interface and frontend integration against approved API contracts.
6. @qa-verifier — independent tests, security checks, API validation, and end-to-end verification.

Before coding, ask every worker to review its responsibility and report:
- requirements and dependencies;
- proposed modules and exact file ownership;
- data it reads and writes;
- API contracts it needs;
- risks and acceptance tests.

Then you, as coordinator, must:
1. inspect the existing repository;
2. resolve conflicts and ambiguities;
3. establish the architecture, database schema, API contracts, and file ownership;
4. create IMPLEMENTATION_PLAN.md and an agent task board;
5. split work into small milestones with acceptance criteria;
6. identify tasks that can safely run in parallel and tasks that must be sequential.

Hard rules:
- Do not start broad implementation until shared contracts are approved.
- Only the coordinator approves changes to shared schemas, migrations, environment configuration, and API contracts.
- No concurrent edits to the same files.
- Keep the application a modular monolith for the MVP; do not add microservices without a demonstrated need.
- Use Next.js + TypeScript, FastAPI + Python, PostgreSQL + SQLAlchemy, and Gemini behind a provider abstraction unless repository inspection reveals a compelling reason to adjust.
- Preserve source document and page provenance for extracted facts, notes, and questions.
- Never expose answer keys to the active test player.
- Validate generated questions and answers; do not treat model output as verified merely because it is valid JSON.
- Do not claim a milestone is complete until tests have actually run and passed.

Return the repository assessment, architecture, data model, API contracts, file ownership matrix, implementation milestones, parallelisation plan, risks, and test strategy. Wait for coordinator review before broad implementation.
```

## 15.4 Implementation prompts by milestone

After reviewing the architecture, ask Antigravity to implement one milestone at a time.

### Prompt M0 — Foundation

```text
Implement only M0 from PRODUCT.md.
Create the frontend shell, FastAPI app, configuration, logging, health endpoint, database connectivity, and test setup.
Do not implement document upload or AI features yet.
Add tests and update README with exact setup and run commands.
Run the backend tests and frontend type checks. Report changed files, commands run, test results, and anything not verified.
```

### Prompt M1 — Upload and library

```text
Implement only M1 from PRODUCT.md.
Build the PDF upload and document library vertical slice.
Validate actual file type and size, calculate SHA-256, store files privately, create database records, and provide list/detail/delete APIs and UI.
Do not implement AI extraction yet.
Add tests for valid upload, invalid extension/content mismatch, oversized file, duplicate hash, missing file, and ownership checks.
Run all relevant tests and report exact results.
```

### Prompt M2 — Extraction

```text
Implement only M2 from PRODUCT.md.
Extract PDFs page-by-page and preserve page numbers. Detect likely scanned/image-only pages and expose an OCR adapter interface. Store extraction results and processing status.
Do not generate notes or questions yet.
Test with at least one text-based PDF and one scanned PDF. Report which pages were extracted and which require OCR/manual review.
```

### Prompt M3 — Structured knowledge

```text
Implement only M3 from PRODUCT.md.
Create Pydantic schemas and an AI provider interface. Add the Gemini adapter behind that interface. Extract topics, concepts, facts, formulas, and questions in structured JSON, preserving page-level source references.
Add schema validation, retry/failure handling, and deduplication safeguards.
Do not add note generation or timed tests yet.
Never silently store malformed or ungrounded AI output as verified.
```

### Prompt M4 — Notes

```text
Implement only M4 from PRODUCT.md.
Generate detailed notes, quick-revision notes, and subject-specific strategy sheets from the validated knowledge records.
Start with Maths, Reasoning, English, and General Awareness templates.
Show source references and label extracted facts separately from AI explanations.
Add tests for note schema validation, source references, empty topics, and regeneration of a single topic.
```

### Prompt M5 — Question bank

```text
Implement only M5 from PRODUCT.md.
Build extracted and AI-generated question banks with topic/difficulty filters and answer explanations.
Create strict question schemas and validation. Ensure single-choice questions have exactly one defensible correct option. Use deterministic checks for arithmetic whenever possible.
Keep answer keys protected from active-test API responses.
Add tests for duplicate questions, ambiguous answers, invalid options, and incorrect answer-key provenance.
```

### Prompt M6 — Timed test

```text
Implement only M6 from PRODUCT.md.
Build the test builder and test player with Speed Challenge, Learning Mode, and basic Exam Simulation.
Speed Challenge should default to 35 seconds per question but allow configuration.
Enforce answer expiry using backend timestamps; do not trust the browser countdown as the authority.
Persist responses safely and handle page refresh. Do not expose correct answers until the attempt is graded.
Add comprehensive timer, scoring, timeout, refresh, and negative-marking tests.
```

### Prompt M7 — Analytics

```text
Implement only M7 from PRODUCT.md.
Calculate scores, accuracy, average time, topic performance, and strong/weak/insufficient-data labels from actual response records.
Create rule-based improvement recommendations, then use AI only to explain those recommendations in clear language.
Do not make unsupported claims about why a student made an error.
Add tests proving every recommendation maps to actual data and that low sample sizes are labelled insufficient data.
```

### Prompt after each milestone — verification

```text
Stop adding features. Review the completed milestone against PRODUCT.md.
Run the complete relevant test suite, type checks, linting, and a local smoke test.
Inspect the user journey in the browser if UI changed.
Find and fix bugs within this milestone only.
Report: requirements met, requirements not met, changed files, commands executed, exact test results, known limitations, and next recommended milestone.
Do not claim success for anything that was not executed and verified.
```

## 15.5 How to work safely and efficiently in Antigravity

- Keep each task narrow enough to review.
- Ask for a plan before large changes.
- Review diffs before accepting significant refactors.
- Commit after each working milestone.
- Use one agent for backend and one for frontend only when their interfaces are already agreed and they can work in separate worktrees or non-overlapping files.
- Do not allow parallel agents to edit the same database models or API contracts without coordination.
- Run tests yourself and inspect the UI; do not rely only on the agent's summary.
- Keep `PRODUCT.md`, `ARCHITECTURE.md`, and `ROADMAP.md` updated as decisions change.

---

# 16. Definition of a successful MVP

The MVP is successful when a student can complete this end-to-end journey without manual developer intervention:

1. Upload an SSC CHSL study PDF or previous-year paper.
2. See the document processing report and any unreadable pages.
3. Open topic-wise detailed notes.
4. Open quick-revision notes and suitable solving strategies.
5. Open extracted and generated questions with traceable answers.
6. Create a test from the question bank.
7. Complete a 35-second-per-question Speed Challenge.
8. See an accurate result report.
9. Identify strong, weak, and insufficient-data topics.
10. Open the relevant notes and launch a targeted practice set.
11. Complete a second test and compare performance.

The strongest proof of value is not that AI generated a large amount of content. It is that the student can answer **new, comparable questions more accurately and/or faster** after following the recommended learning loop.

---

# 17. Immediate next actions

1. Create a GitHub repository named something temporary, such as `ai-exam-coach`.
2. Open that folder in Antigravity.
3. Save this file as `PRODUCT.md` in the repository root.
4. Give Antigravity the planning prompt from section 15.3.
5. Review the proposed architecture before allowing code generation.
6. Implement M0, test it, commit it, then proceed to M1.

**Do not ask Antigravity to build the entire product in one prompt.** Treat the blueprint as the contract and each milestone as a separately testable delivery.

---

# 18. Technical references

Use the current official documentation when implementing the integrations because model names, API methods, quotas, and IDE workflows can change.

- Google Antigravity — Getting started: https://antigravity.google/docs/getting-started
- Google Antigravity — IDE getting started: https://antigravity.google/docs/ide-getting-started
- Gemini API — Getting started and structured output: https://ai.google.dev/gemini-api/docs/get-started
- Gemini API — Files and PDF input: https://ai.google.dev/api/files
- Gemini API — Document processing: https://ai.google.dev/gemini-api/docs/document-processing

**Implementation note:** Verify current API model availability, file-size/page limits, pricing, and data-handling terms before selecting production settings. This blueprint intentionally avoids hardcoding a model name or a fixed API quota.
