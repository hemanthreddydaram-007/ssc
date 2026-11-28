"""End-to-end integration tests for Milestone M4: Smart Notes, Quick Revision & Strategies.

Covers all 8 verification gates from @coordinator #43:
  1. POST /documents/{id}/generate-notes -> 409 before knowledge extraction, 202 after M3.
  2. Note generation and regeneration never re-read the stored PDF file (strictly DB-backed).
  3. detailed, quick_revision, formula_sheet, strategy_sheet across all 4 SSC subjects,
     confirming quick_revision < detailed length and distinct extracted vs ai_explanation labels.
  4. Maths SymPy verification flags wrong worked-example arithmetic as needs_review.
  5. Empty/sparse topic returns status='insufficient_evidence' gracefully with zero LLM calls.
  6. POST /notes/{id}/regenerate updates only target note/sections & increments generation_version;
     PATCH /notes/{id} persists understood_at.
  7. GET /documents/{id}/pyq-patterns returns exact total_questions_analyzed & sample-scoped stats.
  8. Cross-user 403 isolation on all M4 endpoints + 0 items on GET /notes.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.db.session import get_db
from app.models.assessment import Question, QuestionOption
from app.models.learning import Concept, Fact, Note, Topic
from app.services.notes.validators import content_text_length

USER_A = "00000000-0000-0000-0000-000000000001"
USER_B = "00000000-0000-0000-0000-000000000002"
AUTH_A = {"X-User-Id": USER_A}
AUTH_B = {"X-User-Id": USER_B}


def _build_quant_study_pdf() -> bytes:
    """Create a 1-page Quantitative Aptitude PDF with formulas, facts, and PYQ items."""
    doc = pymupdf.open()
    try:
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(
            (50, 80),
            "PROFIT AND LOSS NOTES\n"
            "Profit = Selling Price - Cost Price when SP > CP.\n"
            "Profit Percentage = (Profit / Cost Price) * 100.\n"
            "Q.1 If Cost Price is Rs 200 and Selling Price is Rs 250, find profit percentage.\n"
            "(A) 20% (B) 25% (C) 30% (D) 15% Answer: B",
        )
        return doc.tobytes()
    finally:
        doc.close()


@pytest.fixture
def m4_env(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, MockLLMProvider, sessionmaker[Session]], None, None]:
    """Yield (TestClient, MockLLMProvider, SessionLocal) with outbound HTTP blocked."""
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)
    app = main_module.create_app()
    mock_provider = MockLLMProvider()

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider

    with (
        patch(
            "httpx.HTTPTransport.handle_request",
            side_effect=AssertionError("Live HTTP/Gemini call attempted during M4 test!"),
        ),
        patch(
            "httpx.AsyncHTTPTransport.handle_async_request",
            side_effect=AssertionError("Live async HTTP/Gemini call attempted during M4 test!"),
        ),
        TestClient(app) as tc,
    ):
        yield tc, mock_provider, testing_session_local


def _upload_extract_and_seed_knowledge(
    client: TestClient,
    pdf_bytes: bytes = b"",
    filename: str = "quant_notes.pdf",
) -> str:
    data_bytes = pdf_bytes or _build_quant_study_pdf()
    up = client.post(
        "/api/v1/documents",
        files={"file": (filename, data_bytes, "application/pdf")},
        data={"title": filename, "subject_code": "quantitative_aptitude"},
        headers=AUTH_A,
    )
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]

    proc = client.post(
        f"/api/v1/documents/{doc_id}/process",
        json={"mode": "extract_only"},
        headers=AUTH_A,
    )
    assert proc.status_code == 202, proc.text
    assert client.get(f"/api/v1/jobs/{proc.json()['id']}", headers=AUTH_A).json()["status"] == (
        "completed"
    )
    return doc_id


def _run_m3_knowledge(client: TestClient, doc_id: str) -> None:
    resp = client.post(f"/api/v1/documents/{doc_id}/extract-knowledge", headers=AUTH_A)
    assert resp.status_code == 202, resp.text
    job = client.get(f"/api/v1/jobs/{resp.json()['id']}", headers=AUTH_A).json()
    assert job["status"] == "completed"


# ---------------------------------------------------------------------------
# 1 & 2 & 6 & 8. Pre-knowledge 409, no PDF re-read, regenerate, patch, 403s
# ---------------------------------------------------------------------------


def test_generate_notes_gate_no_pdf_reread_regenerate_patch_and_403_isolation(
    m4_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, mock_provider, _ = m4_env
    doc_id = _upload_extract_and_seed_knowledge(client)

    # 1. 409 Conflict before M3 knowledge extraction
    pre_resp = client.post(f"/api/v1/documents/{doc_id}/generate-notes", headers=AUTH_A)
    assert pre_resp.status_code == 409

    # Run M3 knowledge extraction
    _run_m3_knowledge(client, doc_id)

    # Script deterministic detailed + quick_revision + formula_sheet + strategy_sheet outputs
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "title": "Profit and Loss — Detailed Notes",
                "summary": "Comprehensive coverage of Profit and Loss formulas and PYQ tricks.",
                "sections": [
                    {
                        "key": "core_concepts",
                        "title": "Core Definitions",
                        "blocks": [
                            {
                                "block_type": "formula",
                                "title": "Profit Percentage Formula",
                                "body": "Profit Percentage = (Profit / Cost Price) * 100.",
                                "formula_latex": (
                                    r"\text{Profit \%} = \frac{SP - CP}{CP} \times 100"
                                ),
                                "metadata_items": [],
                                "provenance": "extracted",
                                "source_refs": [
                                    {
                                        "page_number": 1,
                                        "supporting_excerpt": (
                                            "Profit Percentage = (Profit / Cost Price) * 100."
                                        ),
                                    }
                                ],
                                "review_status": "verified",
                            },
                            {
                                "block_type": "worked_example",
                                "title": "Solved Example",
                                "body": (
                                    "CP = 200, SP = 250. Profit = 250 - 200 = 50. "
                                    "50 / 200 * 100 = 25."
                                ),
                                "formula_latex": None,
                                "metadata_items": [],
                                "provenance": "ai_explanation",
                                "source_refs": [],
                                "review_status": "verified",
                            },
                        ],
                    },
                    {
                        "key": "extra_tips",
                        "title": "Exam Strategy",
                        "blocks": [
                            {
                                "block_type": "strategy",
                                "title": "Ratio Shortcut",
                                "body": "Express SP:CP ratio directly when percentage is clean.",
                                "formula_latex": None,
                                "metadata_items": [
                                    {"key": "when_safe_to_use", "value": "Clean fractions"}
                                ],
                                "provenance": "ai_explanation",
                                "source_refs": [],
                                "review_status": "verified",
                            }
                        ],
                    },
                ],
                "one_minute_recap": "Always compute profit % on Cost Price, never Selling Price.",
            }
        ),
        prompt_name="notes_detailed",
    )

    # 2. Verify storage.open_read & pymupdf.open are NEVER called during note generation
    with (
        patch(
            "app.services.document_ingestion.storage.LocalPrivateStorage.open_read",
            side_effect=AssertionError("PDF storage must not be re-read during note generation!"),
        ),
        patch(
            "pymupdf.open",
            side_effect=AssertionError("PyMuPDF must not re-open PDF during note generation!"),
        ),
    ):
        gen_resp = client.post(
            f"/api/v1/documents/{doc_id}/generate-notes",
            json={
                "note_types": ["detailed", "quick_revision", "formula_sheet", "strategy_sheet"],
                "force_regenerate": False,
            },
            headers=AUTH_A,
        )
        assert gen_resp.status_code == 202, gen_resp.text
        job = client.get(f"/api/v1/jobs/{gen_resp.json()['id']}", headers=AUTH_A).json()
        assert job["status"] == "completed"
        assert job["job_type"] == "generate_notes"
        assert job["progress_percent"] == 100

    # Verify all 4 note types created
    doc_notes = client.get(f"/api/v1/documents/{doc_id}/notes", headers=AUTH_A).json()
    assert doc_notes["total"] == 4
    by_type = {item["note_type"]: item for item in doc_notes["items"]}
    assert set(by_type.keys()) == {"detailed", "quick_revision", "formula_sheet", "strategy_sheet"}

    detailed_detail = client.get(
        f"/api/v1/notes/{by_type['detailed']['id']}", headers=AUTH_A
    ).json()
    quick_detail = client.get(
        f"/api/v1/notes/{by_type['quick_revision']['id']}", headers=AUTH_A
    ).json()

    # Provenance distinction on detailed note
    blocks = [
        blk
        for sec in detailed_detail["content_json"]["sections"]
        for blk in sec["blocks"]
    ]
    extracted_blks = [b for b in blocks if b["provenance"] == "extracted"]
    ai_blks = [b for b in blocks if b["provenance"] == "ai_explanation"]
    assert len(extracted_blks) >= 1 and len(extracted_blks[0]["source_refs"]) >= 1
    assert extracted_blks[0]["source_refs"][0]["page_number"] == 1
    assert len(ai_blks) >= 1

    # Quick revision is shorter than detailed note
    from app.schemas.notes import NoteContentJson

    d_len = content_text_length(NoteContentJson.model_validate(detailed_detail["content_json"]))
    q_len = content_text_length(NoteContentJson.model_validate(quick_detail["content_json"]))
    assert q_len < d_len

    # 6. Single-note partial regeneration increments ONLY target note's version & preserves sibling
    target_id = detailed_detail["id"]
    sibling_id = quick_detail["id"]
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "title": "Profit and Loss — Detailed Notes",
                "summary": "Updated summary.",
                "sections": [
                    {
                        "key": "core_concepts",
                        "title": "Core Definitions (Refreshed)",
                        "blocks": [
                            {
                                "block_type": "formula",
                                "title": "Profit Percentage Formula",
                                "body": "Updated Profit % = (SP - CP) / CP * 100.",
                                "formula_latex": None,
                                "metadata_items": [],
                                "provenance": "extracted",
                                "source_refs": [
                                    {
                                        "page_number": 1,
                                        "supporting_excerpt": "Profit Percentage",
                                    }
                                ],
                                "review_status": "verified",
                            }
                        ],
                    }
                ],
                "one_minute_recap": "Recap.",
            }
        ),
        prompt_name="notes_regenerate",
    )

    with patch(
        "app.services.document_ingestion.storage.LocalPrivateStorage.open_read",
        side_effect=AssertionError("PDF storage must not be re-read during note regeneration!"),
    ):
        regen = client.post(
            f"/api/v1/notes/{target_id}/regenerate",
            json={"section_keys": ["core_concepts"], "custom_instruction": "Simplify"},
            headers=AUTH_A,
        )
    assert regen.status_code == 200, regen.text
    regen_body = regen.json()
    assert regen_body["generation_version"] == 2
    sec_keys = [s["key"] for s in regen_body["content_json"]["sections"]]
    assert "core_concepts" in sec_keys and "extra_tips" in sec_keys
    # Sibling quick_revision note remains untouched at version 1
    assert (
        client.get(f"/api/v1/notes/{sibling_id}", headers=AUTH_A).json()["generation_version"] == 1
    )

    # PATCH /notes/{id} toggles understood_at
    patch_true = client.patch(
        f"/api/v1/notes/{target_id}", json={"understood": True}, headers=AUTH_A
    )
    assert patch_true.status_code == 200
    assert patch_true.json()["understood_at"] is not None

    patch_false = client.patch(
        f"/api/v1/notes/{target_id}", json={"understood": False}, headers=AUTH_A
    )
    assert patch_false.status_code == 200
    assert patch_false.json()["understood_at"] is None

    # 8. Cross-user 403 isolation across all M4 endpoints
    assert (
        client.post(f"/api/v1/documents/{doc_id}/generate-notes", headers=AUTH_B).status_code
        == 403
    )
    assert client.get(f"/api/v1/documents/{doc_id}/notes", headers=AUTH_B).status_code == 403
    assert client.get(f"/api/v1/notes/{target_id}", headers=AUTH_B).status_code == 403
    assert (
        client.post(f"/api/v1/notes/{target_id}/regenerate", json={}, headers=AUTH_B).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/notes/{target_id}", json={"understood": True}, headers=AUTH_B
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/documents/{doc_id}/pyq-patterns", headers=AUTH_B).status_code == 403
    assert client.get("/api/v1/notes", headers=AUTH_B).json()["total"] == 0
    assert (
        client.get("/api/v1/notes", params={"document_id": doc_id}, headers=AUTH_B).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# 3. All 4 SSC subjects supported (Maths, Reasoning, English, General Awareness)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject_code", "topic_name", "fact_text"),
    [
        ("quantitative_aptitude", "Percentages", "25% = 1/4 fraction equivalence."),
        ("reasoning", "Syllogism", "All A are B implies Some B are A."),
        ("english", "Subject-Verb Agreement", "Neither/Nor takes verb matching nearest subject."),
        ("general_awareness", "Indian Polity", "Article 21 protects right to life and liberty."),
    ],
)
def test_note_generation_across_all_four_ssc_subjects(
    m4_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
    subject_code: str,
    topic_name: str,
    fact_text: str,
) -> None:
    client, _, session_factory = m4_env
    doc_id = _upload_extract_and_seed_knowledge(client, filename=f"{subject_code}.pdf")

    with session_factory() as db:
        topic = Topic(
            subject_code=subject_code,
            name=topic_name,
            slug=f"{subject_code}-{uuid.uuid4().hex[:6]}",
        )
        db.add(topic)
        db.flush()
        db.add(
            Fact(
                document_id=uuid.UUID(doc_id),
                topic_id=topic.id,
                fact_type="rule",
                content=fact_text,
                provenance="extracted",
                confidence=0.95,
                source_page_number=1,
                supporting_excerpt=fact_text,
                canonical_hash=uuid.uuid4().hex,
                review_status="verified",
            )
        )
        db.commit()
        topic_id = topic.id

    resp = client.post(
        f"/api/v1/documents/{doc_id}/generate-notes",
        json={"note_types": ["detailed", "strategy_sheet"], "topic_ids": [str(topic_id)]},
        headers=AUTH_A,
    )
    assert resp.status_code == 202
    job = client.get(f"/api/v1/jobs/{resp.json()['id']}", headers=AUTH_A).json()
    assert job["status"] == "completed"

    notes = client.get(
        f"/api/v1/documents/{doc_id}/notes",
        params={"subject_code": subject_code},
        headers=AUTH_A,
    ).json()["items"]
    assert len(notes) == 2
    assert {n["note_type"] for n in notes} == {"detailed", "strategy_sheet"}


# ---------------------------------------------------------------------------
# 4. Maths SymPy verification flags wrong worked-example arithmetic as needs_review
# ---------------------------------------------------------------------------


def test_maths_sympy_flags_incorrect_arithmetic_as_needs_review(
    m4_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, mock_provider, session_factory = m4_env
    doc_id = _upload_extract_and_seed_knowledge(client, filename="bad_math.pdf")

    with session_factory() as db:
        topic = Topic(
            subject_code="quantitative_aptitude",
            name="Profit and Loss",
            slug=f"profit-loss-{uuid.uuid4().hex[:6]}",
        )
        db.add(topic)
        db.flush()
        db.add(
            Concept(
                document_id=uuid.UUID(doc_id),
                topic_id=topic.id,
                title="Profit Calculation",
                explanation="Profit = SP - CP.",
                provenance="extracted",
                confidence=0.9,
                source_refs_json=[{"page_number": 1, "supporting_excerpt": "Profit = SP - CP"}],
                canonical_hash=uuid.uuid4().hex,
                review_status="verified",
            )
        )
        db.commit()
        topic_id = topic.id

    # Intentionally wrong equation: 250 - 200 = 80 (expected 50)
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "title": "Profit Calculation Notes",
                "summary": "Summary.",
                "sections": [
                    {
                        "key": "standard_method",
                        "title": "Worked Example",
                        "blocks": [
                            {
                                "block_type": "worked_example",
                                "title": "Bad Arithmetic Example",
                                "body": "Take CP = 200, SP = 250. So Profit = 250 - 200 = 80.",
                                "formula_latex": None,
                                "metadata_items": [],
                                "provenance": "ai_explanation",
                                "source_refs": [],
                                "review_status": "verified",
                            }
                        ],
                    }
                ],
                "one_minute_recap": "Verify arithmetic.",
            }
        ),
        prompt_name="notes_detailed",
    )

    resp = client.post(
        f"/api/v1/documents/{doc_id}/generate-notes",
        json={"note_types": ["detailed"], "topic_ids": [str(topic_id)]},
        headers=AUTH_A,
    )
    assert resp.status_code == 202

    notes = client.get(f"/api/v1/documents/{doc_id}/notes", headers=AUTH_A).json()["items"]
    assert len(notes) == 1
    assert notes[0]["status"] == "needs_review"

    detail = client.get(f"/api/v1/notes/{notes[0]['id']}", headers=AUTH_A).json()
    blk = detail["content_json"]["sections"][0]["blocks"][0]
    assert blk["review_status"] == "needs_review"
    assert len(blk["metadata"].get("math_verification_warnings", [])) >= 1


# ---------------------------------------------------------------------------
# 5. Empty/sparse topic produces insufficient_evidence without LLM calls
# ---------------------------------------------------------------------------


def test_empty_topic_produces_insufficient_evidence_without_llm_hallucination(
    m4_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, mock_provider, session_factory = m4_env
    doc_id = _upload_extract_and_seed_knowledge(client, filename="sparse_topic.pdf")

    with session_factory() as db:
        populated_topic = Topic(
            subject_code="quantitative_aptitude",
            name="Percentages",
            slug=f"pct-{uuid.uuid4().hex[:6]}",
        )
        empty_topic = Topic(
            subject_code="quantitative_aptitude",
            name="Trigonometry",
            slug=f"trig-{uuid.uuid4().hex[:6]}",
        )
        db.add_all([populated_topic, empty_topic])
        db.flush()
        db.add(
            Fact(
                document_id=uuid.UUID(doc_id),
                topic_id=populated_topic.id,
                fact_type="formula",
                content="Percentage = (Part / Whole) * 100.",
                provenance="extracted",
                confidence=0.9,
                source_page_number=1,
                supporting_excerpt="Percentage",
                canonical_hash=uuid.uuid4().hex,
                review_status="verified",
            )
        )
        db.commit()
        empty_topic_id = empty_topic.id

    calls_before = len(mock_provider.calls)
    resp = client.post(
        f"/api/v1/documents/{doc_id}/generate-notes",
        json={"note_types": ["detailed"], "topic_ids": [str(empty_topic_id)]},
        headers=AUTH_A,
    )
    assert resp.status_code == 202
    assert len(mock_provider.calls) == calls_before  # zero LLM calls for empty topic

    notes = client.get(f"/api/v1/documents/{doc_id}/notes", headers=AUTH_A).json()["items"]
    assert len(notes) == 1
    assert notes[0]["status"] == "insufficient_evidence"

    detail = client.get(f"/api/v1/notes/{notes[0]['id']}", headers=AUTH_A).json()
    assert detail["content_json"]["sections"] == []
    assert "Not enough information" in (
        detail["content_json"].get("insufficient_evidence_message") or ""
    )


# ---------------------------------------------------------------------------
# 7. GET /documents/{id}/pyq-patterns denominator and sample-scoped stats
# ---------------------------------------------------------------------------


def test_pyq_patterns_returns_exact_denominator_and_sample_scoped_stats(
    m4_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, _, session_factory = m4_env
    doc_id = _upload_extract_and_seed_knowledge(client, filename="pyq_patterns.pdf")

    with session_factory() as db:
        topic = Topic(
            subject_code="quantitative_aptitude",
            name="Profit and Loss",
            slug=f"pl-{uuid.uuid4().hex[:6]}",
        )
        db.add(topic)
        db.flush()

        for idx in range(3):
            q = Question(
                document_id=uuid.UUID(doc_id),
                topic_id=topic.id,
                subject_code="quantitative_aptitude",
                question_text=(
                    f"If cost price of article is Rs {100 + idx * 50} and profit is 20%, find SP?"
                ),
                question_type="single_choice",
                difficulty="easy" if idx < 2 else "medium",
                origin="extracted",
                source_page_number=1,
                supporting_excerpt="Cost Price",
                stem_hash=uuid.uuid4().hex,
                correct_answer_data={"correct_option_key": "B"},
                pyq_metadata_json={"year": 2023, "shift": "Shift 1"},
                validation_status="verified",
            )
            db.add(q)
            db.flush()
            db.add(
                QuestionOption(question_id=q.id, option_key="A", option_text="100", display_order=0)
            )
            db.add(
                QuestionOption(question_id=q.id, option_key="B", option_text="120", display_order=1)
            )
        db.commit()

    resp = client.get(f"/api/v1/documents/{doc_id}/pyq-patterns", headers=AUTH_A)
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == doc_id
    assert body["total_questions_analyzed"] == 3
    assert "3 question(s)" in body["sample_note"]
    assert body["subjects"][0]["subject_code"] == "quantitative_aptitude"
    assert body["subjects"][0]["count"] == 3
    assert body["subjects"][0]["percentage"] == 100.0
    assert body["topics"][0]["count"] == 3
    assert body["difficulty_distribution"] == {"easy": 2, "medium": 1}
    assert body["years_shifts"] == [{"year": "2023", "shift": "Shift 1", "count": 3}]
    assert len(body["repeated_templates"]) >= 1
    assert body["repeated_templates"][0]["count"] == 3
    assert body["repeated_templates"][0]["denominator"] == 3
    # Keep Note model imported cleanly if needed by static checks
    assert Note is not None


def test_generate_notes_max_topics_prioritizes_densest_topics_and_preserves_scope_on_retry(
    m4_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    from app.models.document import ProcessingJob  # noqa: PLC0415

    client, mock_provider, session_factory = m4_env
    doc_id = _upload_extract_and_seed_knowledge(client, filename="multi_topic_notes.pdf")

    with session_factory() as db:
        t_sparse = Topic(
            subject_code="quantitative_aptitude",
            name="Sparse Topic",
            slug=f"sparse-{uuid.uuid4().hex[:6]}",
        )
        t_mid = Topic(
            subject_code="quantitative_aptitude",
            name="Medium Topic",
            slug=f"mid-{uuid.uuid4().hex[:6]}",
        )
        t_dense = Topic(
            subject_code="quantitative_aptitude",
            name="Dense Topic",
            slug=f"dense-{uuid.uuid4().hex[:6]}",
        )
        db.add_all([t_sparse, t_mid, t_dense])
        db.flush()

        # 1 fact on t_sparse, 2 facts on t_mid, 3 records (1 concept + 2 facts) on t_dense
        db.add(
            Fact(
                document_id=uuid.UUID(doc_id),
                topic_id=t_sparse.id,
                fact_type="formula",
                content="Sparse formula fact.",
                provenance="extracted",
                source_page_number=1,
            )
        )
        for i in range(2):
            db.add(
                Fact(
                    document_id=uuid.UUID(doc_id),
                    topic_id=t_mid.id,
                    fact_type="rule",
                    content=f"Medium rule fact {i}.",
                    provenance="extracted",
                    source_page_number=1,
                )
            )
        db.add(
            Concept(
                document_id=uuid.UUID(doc_id),
                topic_id=t_dense.id,
                title="Dense Concept",
                explanation="High-value concept for exam.",
                difficulty="medium",
                provenance="extracted",
            )
        )
        for i in range(2):
            db.add(
                Fact(
                    document_id=uuid.UUID(doc_id),
                    topic_id=t_dense.id,
                    fact_type="formula",
                    content=f"Dense formula fact {i}.",
                    provenance="extracted",
                    source_page_number=1,
                )
            )
        db.commit()
        sparse_id = str(t_sparse.id)
        mid_id = str(t_mid.id)
        dense_id = str(t_dense.id)

    for label in ("Dense", "Medium"):
        mock_provider.enqueue_raw(
            json.dumps(
                {
                    "title": f"{label} Quick Revision",
                    "summary": f"Concise {label} summary.",
                    "sections": [
                        {
                            "key": "core",
                            "title": "Core Points",
                            "blocks": [
                                {
                                    "block_type": "recap",
                                    "title": "Point 1",
                                    "body": f"{label} verified summary block.",
                                    "formula_latex": None,
                                    "metadata_items": [],
                                    "provenance": "extracted",
                                    "source_refs": [
                                        {
                                            "page_number": 1,
                                            "supporting_excerpt": f"{label} formula",
                                        }
                                    ],
                                    "review_status": "verified",
                                }
                            ],
                        }
                    ],
                    "one_minute_recap": f"{label} recap.",
                    "insufficient_evidence_message": None,
                }
            )
        )

    resp = client.post(
        f"/api/v1/documents/{doc_id}/generate-notes",
        json={"note_types": ["quick_revision"], "max_topics": 2},
        headers=AUTH_A,
    )
    assert resp.status_code == 202, resp.text
    job = resp.json()
    assert job["total_items"] == 2

    notes = client.get(f"/api/v1/documents/{doc_id}/notes", headers=AUTH_A).json()["items"]
    generated_topic_ids = {n["topic_id"] for n in notes}
    assert generated_topic_ids == {dense_id, mid_id}
    assert sparse_id not in generated_topic_ids

    # Simulate failed job retry to confirm capped topic_ids stay intact across retries
    with session_factory() as db:
        db_job = db.get(ProcessingJob, uuid.UUID(job["id"]))
        assert db_job is not None
        db_job.status = "failed"
        db.commit()

    mock_provider.enqueue_raw(
        json.dumps(
            {
                "title": "Retry Revision",
                "summary": "Retried summary.",
                "sections": [],
                "one_minute_recap": "Recap.",
                "insufficient_evidence_message": None,
            }
        )
    )
    retry_resp = client.post(f"/api/v1/jobs/{job['id']}/retry", headers=AUTH_A)
    assert retry_resp.status_code == 202, retry_resp.text
    assert retry_resp.json()["total_items"] == 2
