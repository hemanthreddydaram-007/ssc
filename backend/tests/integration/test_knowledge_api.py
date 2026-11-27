"""End-to-end integration tests for Milestone M3: AI Provider & Structured Knowledge Extraction.

Covers all 7 verification gates from @coordinator #38:
  1. Upload PDF -> POST /process (extract_only) -> POST /extract-knowledge via
     app.dependency_overrides[get_llm_provider] with deterministic MockLLMProvider (zero live AI).
  2. 409 Conflict when POST /extract-knowledge is called before page extraction.
  3. LLMProvider 1-retry repair flow + double-failure failed_validation quarantine
     + AIGenerationRun logging + Question validation_status='needs_review' quarantine.
  4. 'unknown' subject/topic classification allowed + PATCH /classification override persists.
  5. Extracted facts, concepts, and questions retain document_id + valid source_page_number
     + supporting_excerpt; QuestionOption never exposes is_correct.
  6. Reprocessing (force_reprocess=true & false) produces zero duplicate facts/concepts/questions;
     conflicting fact values remain separate with review_status='conflict' & conflict_group_id.
  7. PATCH /facts/{id} + cross-user 403 ownership enforcement across all M3 endpoints.
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
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.db.session import get_db
from app.models.learning import AIGenerationRun, Concept, Fact

USER_A = "00000000-0000-0000-0000-000000000001"
USER_B = "00000000-0000-0000-0000-000000000002"
AUTH_A = {"X-User-Id": USER_A}
AUTH_B = {"X-User-Id": USER_B}


def _build_polity_study_pdf() -> bytes:
    """Create a 2-page SSC CHSL polity PDF with facts, concepts, and an MCQ."""
    doc = pymupdf.open()
    try:
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(
            (50, 100),
            "INDIAN CONSTITUTION NOTES\n"
            "Article 17 of the Constitution abolishes untouchability in all forms.\n"
            "The 42nd Amendment Act of 1976 added Fundamental Duties under Part IV-A.",
        )
        p2 = doc.new_page(width=595, height=842)
        p2.insert_text(
            (50, 100),
            "Q.1 Which Article of the Indian Constitution abolishes untouchability?\n"
            "(A) Article 14\n(B) Article 17\n(C) Article 19\n(D) Article 21\n"
            "Answer Key: (B) Article 17",
        )
        return doc.tobytes()
    finally:
        doc.close()


def _build_unknown_subject_pdf() -> bytes:
    """Create a 1-page PDF with generic prose that carries no exam-subject keywords."""
    doc = pymupdf.open()
    try:
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(
            (50, 100),
            "Miscellaneous personal checklist and packing reminders for weekend travel.",
        )
        return doc.tobytes()
    finally:
        doc.close()


@pytest.fixture
def m3_env(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, MockLLMProvider, sessionmaker[Session]], None, None]:
    """Yield (TestClient, MockLLMProvider, SessionLocal) with get_llm_provider overridden."""
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
            side_effect=AssertionError("Live HTTP/Gemini call attempted during M3 test!"),
        ),
        patch(
            "httpx.AsyncHTTPTransport.handle_async_request",
            side_effect=AssertionError("Live async HTTP/Gemini call attempted during M3 test!"),
        ),
        TestClient(app) as tc,
    ):
        yield tc, mock_provider, testing_session_local


def _upload_and_extract(client: TestClient, pdf_bytes: bytes, filename: str = "study.pdf") -> str:
    upload = client.post(
        "/api/v1/documents",
        files={"file": (filename, pdf_bytes, "application/pdf")},
        data={"title": filename},
        headers=AUTH_A,
    )
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["id"]

    proc = client.post(
        f"/api/v1/documents/{doc_id}/process",
        json={"mode": "extract_only"},
        headers=AUTH_A,
    )
    assert proc.status_code == 202, proc.text
    job = client.get(f"/api/v1/jobs/{proc.json()['id']}", headers=AUTH_A).json()
    assert job["status"] == "completed"
    return doc_id


# ---------------------------------------------------------------------------
# 1 & 5 & 7. End-to-end pipeline + provenance + no is_correct + PATCH /facts + 403
# ---------------------------------------------------------------------------


def test_end_to_end_extract_knowledge_provenance_fact_patch_and_403_isolation(
    m3_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, mock_provider, session_factory = m3_env
    doc_id = _upload_and_extract(client, _build_polity_study_pdf(), "polity.pdf")

    # Script deterministic structured extraction outputs for the 2 chunks + classification
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "subject_code": "general_awareness",
                "material_type": "notes",
                "language": "en",
                "confidence": 0.94,
                "topic_candidates": ["Indian Polity"],
                "rationale": "Contains Constitutional Articles and Amendments.",
            }
        ),
        prompt_name="document_classification",
    )
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "detected_subject_code": "general_awareness",
                "facts": [
                    {
                        "fact_type": "rule",
                        "content": "Article 17 abolishes untouchability in all forms.",
                        "topic_name": "Indian Polity",
                        "source_page_number": 1,
                        "supporting_excerpt": (
                            "Article 17 of the Constitution abolishes untouchability in all forms."
                        ),
                        "provenance": "extracted",
                        "confidence": 0.95,
                        "is_time_sensitive": False,
                        "source_date_label": None,
                    }
                ],
                "concepts": [
                    {
                        "title": "Right to Equality — Article 17",
                        "explanation": "Constitutional prohibition of untouchability.",
                        "topic_name": "Indian Polity",
                        "difficulty": "easy",
                        "source_page_number": 1,
                        "supporting_excerpt": (
                            "Article 17 of the Constitution abolishes untouchability in all forms."
                        ),
                        "provenance": "extracted",
                        "confidence": 0.9,
                        "prerequisites": ["Fundamental Rights"],
                        "related_concepts": ["Article 14"],
                    }
                ],
                "questions": [],
            }
        ),
        prompt_name="knowledge_extraction",
    )
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "detected_subject_code": "general_awareness",
                "facts": [],
                "concepts": [],
                "questions": [
                    {
                        "question_text": (
                            "Which Article of the Indian Constitution abolishes untouchability?"
                        ),
                        "question_type": "single_choice",
                        "subject_code": "general_awareness",
                        "topic_name": "Indian Polity",
                        "difficulty": "easy",
                        "options": [
                            {"key": "A", "text": "Article 14"},
                            {"key": "B", "text": "Article 17"},
                            {"key": "C", "text": "Article 19"},
                            {"key": "D", "text": "Article 21"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "Article 17 abolishes untouchability.",
                        "source_page_number": 2,
                        "supporting_excerpt": (
                            "Q.1 Which Article of the Indian Constitution abolishes untouchability?"
                        ),
                        "answer_key_provenance": "source_answer_key",
                    }
                ],
            }
        ),
        prompt_name="knowledge_extraction",
    )

    resp = client.post(
        f"/api/v1/documents/{doc_id}/extract-knowledge",
        json={"force_reprocess": False},
        headers=AUTH_A,
    )
    assert resp.status_code == 202, resp.text
    job = client.get(f"/api/v1/jobs/{resp.json()['id']}", headers=AUTH_A).json()
    assert job["status"] == "completed"
    assert job["job_type"] == "extract_knowledge"
    assert job["progress_percent"] == 100
    assert [s["name"] for s in job["stages"]] == [
        "classification",
        "knowledge_extraction",
        "grounding_dedup",
        "question_ingestion",
    ]
    assert all(s["status"] == "completed" for s in job["stages"])

    # Knowledge read endpoint
    k_resp = client.get(f"/api/v1/documents/{doc_id}/knowledge", headers=AUTH_A)
    assert k_resp.status_code == 200
    knowledge = k_resp.json()
    assert knowledge["document_id"] == doc_id
    assert knowledge["detected_subject_code"] == "general_awareness"
    assert knowledge["rejected_or_uncertain_count"] == 0
    assert len(knowledge["facts"]) == 1
    assert len(knowledge["concepts"]) == 1
    assert len(knowledge["topics"]) >= 1

    fact = knowledge["facts"][0]
    assert fact["document_id"] == doc_id
    assert fact["source_page_number"] == 1
    assert "Article 17" in (fact["supporting_excerpt"] or "")
    assert fact["review_status"] == "verified"

    concept = knowledge["concepts"][0]
    assert concept["document_id"] == doc_id
    assert len(concept["source_refs_json"]) >= 1
    assert concept["source_refs_json"][0]["page_number"] == 1
    assert "Article 17" in (concept["source_refs_json"][0]["supporting_excerpt"] or "")

    # Questions endpoint & no is_correct leak on QuestionOption
    q_resp = client.get(f"/api/v1/documents/{doc_id}/questions", headers=AUTH_A)
    assert q_resp.status_code == 200
    q_body = q_resp.json()
    assert q_body["total"] == 1
    q_item = q_body["items"][0]
    assert q_item["document_id"] == doc_id
    assert q_item["source_page_number"] == 2
    assert "untouchability" in (q_item["supporting_excerpt"] or "").lower()
    assert q_item["validation_status"] == "verified"
    assert len(q_item["options"]) == 4
    for opt in q_item["options"]:
        assert "is_correct" not in opt

    # Global questions filter + topics + subjects endpoints
    assert (
        client.get("/api/v1/questions", params={"subject_code": "general_awareness"}).json()[
            "total"
        ]
        == 1
    )
    assert client.get(f"/api/v1/documents/{doc_id}/topics", headers=AUTH_A).json()["total"] >= 1
    assert client.get("/api/v1/topics", headers=AUTH_A).json()["total"] >= 1
    subjects = client.get("/api/v1/subjects", headers=AUTH_A).json()["items"]
    assert any(s["subject_code"] == "general_awareness" for s in subjects)

    # AIGenerationRun rows persisted
    with session_factory() as db:
        runs = (
            db.execute(
                select(AIGenerationRun).where(AIGenerationRun.document_id == uuid.UUID(doc_id))
            )
            .scalars()
            .all()
        )
        assert len(runs) >= 3
        assert {r.stage for r in runs} >= {"classification", "knowledge_extraction"}
        assert all(r.validation_status == "valid" for r in runs)

    # PATCH /facts/{id} updates content & review_status
    fact_id = fact["id"]
    patch_fact = client.patch(
        f"/api/v1/facts/{fact_id}",
        json={
            "content": "Article 17 strictly abolishes untouchability and forbids its practice.",
            "fact_type": "constitutional_article",
            "review_status": "verified",
        },
        headers=AUTH_A,
    )
    assert patch_fact.status_code == 200
    assert patch_fact.json()["fact_type"] == "constitutional_article"
    assert "strictly abolishes" in patch_fact.json()["content"]

    # Cross-user 403 ownership enforcement on ALL M3 endpoints
    assert (
        client.post(f"/api/v1/documents/{doc_id}/extract-knowledge", headers=AUTH_B).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/documents/{doc_id}/classification",
            json={"subject_code": "english"},
            headers=AUTH_B,
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/documents/{doc_id}/knowledge", headers=AUTH_B).status_code == 403
    assert client.get(f"/api/v1/documents/{doc_id}/topics", headers=AUTH_B).status_code == 403
    assert client.get(f"/api/v1/documents/{doc_id}/questions", headers=AUTH_B).status_code == 403
    assert (
        client.get("/api/v1/questions", params={"document_id": doc_id}, headers=AUTH_B).status_code
        == 403
    )
    assert client.get("/api/v1/questions", headers=AUTH_B).json()["total"] == 0
    assert (
        client.patch(
            f"/api/v1/facts/{fact_id}",
            json={"review_status": "rejected"},
            headers=AUTH_B,
        ).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# 2. 409 Conflict before page extraction
# ---------------------------------------------------------------------------


def test_extract_knowledge_before_page_extraction_returns_409(
    m3_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, _, _ = m3_env
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("unprocessed.pdf", _build_polity_study_pdf(), "application/pdf")},
        headers=AUTH_A,
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    resp = client.post(f"/api/v1/documents/{doc_id}/extract-knowledge", headers=AUTH_A)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 3. 1-retry repair + double-failure failed_validation quarantine + needs_review
# ---------------------------------------------------------------------------


def test_llm_repair_and_double_failure_quarantine_and_needs_review_questions(
    m3_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, mock_provider, session_factory = m3_env
    doc_id = _upload_and_extract(client, _build_polity_study_pdf(), "repair_test.pdf")

    # Classification succeeds cleanly
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "subject_code": "general_awareness",
                "material_type": "pyq_paper",
                "language": "en",
                "confidence": 0.9,
                "topic_candidates": ["Indian Polity"],
                "rationale": "Polity PYQ.",
            }
        ),
        prompt_name="document_classification",
    )

    # Chunk 1: malformed JSON first, then valid repaired JSON on 2nd attempt!
    # Also returns an incomplete question (missing correct_option_key) -> needs_review
    mock_provider.enqueue_raw("{not-valid-json", prompt_name="knowledge_extraction")
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "detected_subject_code": "general_awareness",
                "facts": [
                    {
                        "fact_type": "event",
                        "content": "42nd Amendment Act of 1976 added Fundamental Duties.",
                        "topic_name": "Indian Polity",
                        "source_page_number": 1,
                        "supporting_excerpt": "42nd Amendment Act of 1976 added Fundamental Duties",
                        "provenance": "extracted",
                        "confidence": 0.91,
                    }
                ],
                "concepts": [],
                "questions": [
                    {
                        "question_text": "Unkeyed question missing answer key?",
                        "question_type": "single_choice",
                        "subject_code": "general_awareness",
                        "topic_name": "Indian Polity",
                        "difficulty": "medium",
                        "options": [
                            {"key": "A", "text": "Opt 1"},
                            {"key": "B", "text": "Opt 2"},
                            {"key": "C", "text": "Opt 3"},
                            {"key": "D", "text": "Opt 4"},
                        ],
                        "correct_option_key": None,
                        "supporting_excerpt": "",
                        "answer_key_provenance": "unverified",
                    }
                ],
            }
        ),
        prompt_name="knowledge_extraction:repair",
    )

    # Chunk 2: malformed on BOTH initial call AND repair call -> failed_validation quarantine!
    mock_provider.enqueue_raw('{"detected_subject_code": 123', prompt_name="knowledge_extraction")
    mock_provider.enqueue_raw("still not valid json!!", prompt_name="knowledge_extraction:repair")

    resp = client.post(f"/api/v1/documents/{doc_id}/extract-knowledge", headers=AUTH_A)
    assert resp.status_code == 202
    job = client.get(f"/api/v1/jobs/{resp.json()['id']}", headers=AUTH_A).json()
    assert job["status"] == "completed"
    stage_by_name = {s["name"]: s for s in job["stages"]}
    assert "failed schema validation" in (
        stage_by_name["knowledge_extraction"]["error_message"] or ""
    )

    with session_factory() as db:
        runs = (
            db.execute(
                select(AIGenerationRun)
                .where(
                    AIGenerationRun.document_id == uuid.UUID(doc_id),
                    AIGenerationRun.stage == "knowledge_extraction",
                )
                .order_by(AIGenerationRun.created_at)
            )
            .scalars()
            .all()
        )
        statuses = [r.validation_status for r in runs]
        assert "repaired" in statuses
        assert "failed_validation" in statuses

        # Chunk 1's repaired fact stored; Chunk 2 produced zero corrupted facts
        facts = (
            db.execute(select(Fact).where(Fact.document_id == uuid.UUID(doc_id))).scalars().all()
        )
        assert len(facts) == 1
        assert "42nd Amendment" in facts[0].content

    # Incomplete question quarantined as needs_review (not verified)
    q_items = client.get(f"/api/v1/documents/{doc_id}/questions", headers=AUTH_A).json()["items"]
    assert len(q_items) == 1
    assert q_items[0]["validation_status"] == "needs_review"
    assert q_items[0]["correct_option_key"] is None


# ---------------------------------------------------------------------------
# 4. Unknown classification allowed + manual override persists
# ---------------------------------------------------------------------------


def test_unknown_classification_allowed_and_manual_override_persists(
    m3_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, _, _ = m3_env
    doc_id = _upload_and_extract(client, _build_unknown_subject_pdf(), "misc.pdf")

    # Default MockLLMProvider finds no subject keywords -> classifies as "unknown"
    resp = client.post(f"/api/v1/documents/{doc_id}/extract-knowledge", headers=AUTH_A)
    assert resp.status_code == 202
    job = client.get(f"/api/v1/jobs/{resp.json()['id']}", headers=AUTH_A).json()
    assert job["status"] == "completed"

    knowledge = client.get(f"/api/v1/documents/{doc_id}/knowledge", headers=AUTH_A).json()
    assert knowledge["detected_subject_code"] == "unknown"
    assert knowledge["subject_code"] in (None, "unknown")

    # User manually overrides subject, material_type, language
    override = client.patch(
        f"/api/v1/documents/{doc_id}/classification",
        json={
            "subject_code": "reasoning",
            "material_type": "formula_sheet",
            "language": "en",
        },
        headers=AUTH_A,
    )
    assert override.status_code == 200
    ov_body = override.json()
    assert ov_body["subject_code"] == "reasoning"
    assert ov_body["detected_subject_code"] == "unknown"
    assert ov_body["material_type"] == "formula_sheet"

    # Override persists across subsequent GET /documents/{id}/knowledge & GET /documents/{id}
    doc_get = client.get(f"/api/v1/documents/{doc_id}", headers=AUTH_A).json()
    assert doc_get["subject_code"] == "reasoning"
    assert (
        client.get(f"/api/v1/documents/{doc_id}/knowledge", headers=AUTH_A).json()["subject_code"]
        == "reasoning"
    )


# ---------------------------------------------------------------------------
# 6. Reprocessing deduplication + conflicting facts kept separate
# ---------------------------------------------------------------------------


def test_reprocessing_dedup_and_conflicting_facts_stay_separate(
    m3_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, mock_provider, session_factory = m3_env
    doc_id = _upload_and_extract(client, _build_polity_study_pdf(), "conflict_dedup.pdf")

    def _script_conflicting_run() -> None:
        mock_provider.enqueue_raw(
            json.dumps(
                {
                    "subject_code": "general_awareness",
                    "material_type": "notes",
                    "language": "en",
                    "confidence": 0.95,
                    "topic_candidates": ["Indian Polity"],
                    "rationale": "Polity notes.",
                }
            ),
            prompt_name="document_classification",
        )
        # Chunk 1 emits two conflicting facts about Fundamental Duties Amendment year + 1 concept
        mock_provider.enqueue_raw(
            json.dumps(
                {
                    "detected_subject_code": "general_awareness",
                    "facts": [
                        {
                            "fact_type": "date",
                            "content": (
                                "Fundamental Duties were added by the 42nd Amendment in 1976."
                            ),
                            "topic_name": "Indian Polity",
                            "source_page_number": 1,
                            "supporting_excerpt": (
                                "42nd Amendment Act of 1976 added Fundamental Duties"
                            ),
                            "provenance": "extracted",
                            "confidence": 0.92,
                        },
                        {
                            "fact_type": "date",
                            "content": (
                                "Fundamental Duties were added by the 44th Amendment in 1978."
                            ),
                            "topic_name": "Indian Polity",
                            "source_page_number": 1,
                            "supporting_excerpt": (
                                "42nd Amendment Act of 1976 added Fundamental Duties"
                            ),
                            "provenance": "extracted",
                            "confidence": 0.72,
                        },
                    ],
                    "concepts": [
                        {
                            "title": "Fundamental Duties",
                            "explanation": "Added to Part IV-A of the Constitution.",
                            "topic_name": "Indian Polity",
                            "difficulty": "medium",
                            "source_page_number": 1,
                            "supporting_excerpt": "added Fundamental Duties under Part IV-A",
                            "provenance": "extracted",
                            "confidence": 0.9,
                        }
                    ],
                    "questions": [],
                }
            ),
            prompt_name="knowledge_extraction",
        )
        # Chunk 2 emits the same question both runs
        mock_provider.enqueue_raw(
            json.dumps(
                {
                    "detected_subject_code": "general_awareness",
                    "facts": [],
                    "concepts": [],
                    "questions": [
                        {
                            "question_text": (
                                "Which Article of the Indian Constitution abolishes untouchability?"
                            ),
                            "question_type": "single_choice",
                            "subject_code": "general_awareness",
                            "topic_name": "Indian Polity",
                            "difficulty": "easy",
                            "options": [
                                {"key": "A", "text": "Article 14"},
                                {"key": "B", "text": "Article 17"},
                                {"key": "C", "text": "Article 19"},
                                {"key": "D", "text": "Article 21"},
                            ],
                            "correct_option_key": "B",
                            "supporting_excerpt": (
                                "Which Article of the Indian Constitution abolishes untouchability?"
                            ),
                            "answer_key_provenance": "source_answer_key",
                        }
                    ],
                }
            ),
            prompt_name="knowledge_extraction",
        )

    # Run 1
    _script_conflicting_run()
    r1 = client.post(
        f"/api/v1/documents/{doc_id}/extract-knowledge",
        json={"force_reprocess": False},
        headers=AUTH_A,
    )
    assert r1.status_code == 202

    k1 = client.get(f"/api/v1/documents/{doc_id}/knowledge", headers=AUTH_A).json()
    assert len(k1["facts"]) == 2
    assert all(f["review_status"] == "conflict" for f in k1["facts"])
    group_ids = {f["conflict_group_id"] for f in k1["facts"]}
    assert len(group_ids) == 1 and None not in group_ids
    assert k1["rejected_or_uncertain_count"] >= 2
    assert len(k1["concepts"]) == 1
    assert client.get(f"/api/v1/documents/{doc_id}/questions", headers=AUTH_A).json()["total"] == 1

    # Run 2 with force_reprocess=True -> clear_document_knowledge + stem_hash dedup -> 0 dups
    _script_conflicting_run()
    r2 = client.post(
        f"/api/v1/documents/{doc_id}/extract-knowledge",
        json={"force_reprocess": True},
        headers=AUTH_A,
    )
    assert r2.status_code == 202

    # Run 3 with force_reprocess=False -> canonical_hash & stem_hash dedup -> STILL no duplicates!
    _script_conflicting_run()
    r3 = client.post(
        f"/api/v1/documents/{doc_id}/extract-knowledge",
        json={"force_reprocess": False},
        headers=AUTH_A,
    )
    assert r3.status_code == 202

    k3 = client.get(f"/api/v1/documents/{doc_id}/knowledge", headers=AUTH_A).json()
    assert len(k3["facts"]) == 2
    assert len(k3["concepts"]) == 1
    assert client.get(f"/api/v1/documents/{doc_id}/questions", headers=AUTH_A).json()["total"] == 1

    with session_factory() as db:
        db_concepts = (
            db.execute(select(Concept).where(Concept.document_id == uuid.UUID(doc_id)))
            .scalars()
            .all()
        )
        assert len(db_concepts) == 1
