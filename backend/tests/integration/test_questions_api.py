"""End-to-end integration tests for Milestone M5: Question Bank & Validation.

Covers all 4 verification gates from @coordinator #48:
  1. POST /api/v1/questions/generate via MockLLMProvider (zero live HTTP): 4 distinct options,
     1 valid answer, AIGenerationRun logging, SymPy wrong-arithmetic -> needs_review,
     canonical numeric distractor collision (0.5 vs 1/2 vs 50%) -> needs_review, duplicate skip.
  2. POST /api/v1/questions/import (JSON & CSV): preserves pyq_metadata_json, passage_group_id /
     passage_text, answer_key_provenance; user_supplied keys NOT blindly marked verified;
     near-duplicate stem skipped.
  3. Bank filters (subject_code, topic_id, difficulty, origin, validation_status, pyq_year, q),
     GET /questions/{id} detail, PATCH sets answer_key_provenance='manual' on key edit,
     DELETE removes question while preserving existing TestQuestion snapshot.
  4. Answer-key safety (no is_correct on options, no correct_answer_data on list),
     cross-user 403 isolation, and POST /api/v1/exam-configs create (201) + duplicate (409).
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
from app.models.assessment import Test as TestModel
from app.models.assessment import TestQuestion as TestQuestionModel
from app.models.learning import AIGenerationRun, Fact, Topic

USER_A = "00000000-0000-0000-0000-000000000001"
USER_B = "00000000-0000-0000-0000-000000000002"
AUTH_A = {"X-User-Id": USER_A}
AUTH_B = {"X-User-Id": USER_B}


def _build_seed_pdf() -> bytes:
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=595, height=842)
        page.insert_text(
            (50, 80),
            "PERCENTAGES AND FRACTIONS\n25% of 200 equals 50.\n0.5 equals 1/2 and 50%.",
        )
        return doc.tobytes()
    finally:
        doc.close()


@pytest.fixture
def m5_env(
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
            side_effect=AssertionError("Live HTTP/Gemini call attempted during M5 test!"),
        ),
        patch(
            "httpx.AsyncHTTPTransport.handle_async_request",
            side_effect=AssertionError("Live async HTTP/Gemini call attempted during M5 test!"),
        ),
        TestClient(app) as tc,
    ):
        yield tc, mock_provider, testing_session_local


def _seed_doc_with_knowledge(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> tuple[str, str]:
    up = client.post(
        "/api/v1/documents",
        files={"file": ("quant.pdf", _build_seed_pdf(), "application/pdf")},
        data={"title": "Quant Notes", "subject_code": "quantitative_aptitude"},
        headers=AUTH_A,
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]

    proc = client.post(
        f"/api/v1/documents/{doc_id}/process",
        json={"mode": "extract_only"},
        headers=AUTH_A,
    )
    assert proc.status_code == 202

    with session_factory() as db:
        topic = Topic(
            subject_code="quantitative_aptitude",
            name="Percentages",
            slug=f"percentages-{uuid.uuid4().hex[:6]}",
        )
        db.add(topic)
        db.flush()
        db.add(
            Fact(
                document_id=uuid.UUID(doc_id),
                topic_id=topic.id,
                fact_type="formula",
                content="x% of y = (x / 100) * y; 25% of 200 = 50.",
                provenance="extracted",
                confidence=0.95,
                source_page_number=1,
                supporting_excerpt="25% of 200 equals 50",
                canonical_hash=uuid.uuid4().hex,
                review_status="verified",
            )
        )
        db.commit()
        topic_id = str(topic.id)

    return doc_id, topic_id


# ---------------------------------------------------------------------------
# 1. Question generation + SymPy math check + canonical distractor + dedup
# ---------------------------------------------------------------------------


def test_generate_questions_validation_math_distractors_dedup_and_ai_run(
    m5_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, mock_provider, session_factory = m5_env
    doc_id, topic_id = _seed_doc_with_knowledge(client, session_factory)

    mock_provider.enqueue_raw(
        json.dumps(
            {
                "questions": [
                    {
                        # Valid deterministic question
                        "question_text": "What is 25% of 200?",
                        "difficulty": "easy",
                        "topic_name": "Percentages",
                        "options": [
                            {"key": "A", "text": "40"},
                            {"key": "B", "text": "50"},
                            {"key": "C", "text": "60"},
                            {"key": "D", "text": "75"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "25% of 200 = 50.",
                        "source_page_number": 1,
                        "supporting_excerpt": "25% of 200 equals 50",
                    },
                    {
                        # Wrong keyed arithmetic: 20% of 150 = 30, keyed to A (20) -> needs_review
                        "question_text": "Calculate 20% of 150.",
                        "difficulty": "easy",
                        "topic_name": "Percentages",
                        "options": [
                            {"key": "A", "text": "20"},
                            {"key": "B", "text": "30"},
                            {"key": "C", "text": "45"},
                            {"key": "D", "text": "50"},
                        ],
                        "correct_option_key": "A",
                        "explanation": "20% of 150 = 30.",
                        "source_page_number": 1,
                        "supporting_excerpt": "25% of 200 equals 50",
                    },
                    {
                        # Canonical numeric distractor collision: 0.5 == 1/2 == 50% -> needs_review
                        "question_text": "Which fraction equals half of a whole?",
                        "difficulty": "medium",
                        "topic_name": "Percentages",
                        "options": [
                            {"key": "A", "text": "0.5"},
                            {"key": "B", "text": "1/2"},
                            {"key": "C", "text": "50%"},
                            {"key": "D", "text": "0.25"},
                        ],
                        "correct_option_key": "A",
                        "explanation": "Half equals 0.5.",
                        "source_page_number": 1,
                        "supporting_excerpt": "0.5 equals 1/2 and 50%",
                    },
                    {
                        # Exact duplicate stem in same batch -> skipped
                        "question_text": "What is 25% of 200?",
                        "difficulty": "easy",
                        "topic_name": "Percentages",
                        "options": [
                            {"key": "A", "text": "40"},
                            {"key": "B", "text": "50"},
                            {"key": "C", "text": "60"},
                            {"key": "D", "text": "75"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "Duplicate.",
                        "source_page_number": 1,
                        "supporting_excerpt": "25% of 200 equals 50",
                    },
                ]
            }
        ),
        prompt_name="question_generate",
    )

    resp = client.post(
        "/api/v1/questions/generate",
        json={"document_id": doc_id, "topic_id": topic_id, "difficulty": "mixed", "count": 4},
        headers=AUTH_A,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["created"]) == 3
    assert body["verified_count"] == 1
    assert body["needs_review_count"] == 2
    assert body["duplicates_skipped"] == 1

    by_stem = {q["question_text"]: q for q in body["created"]}
    assert by_stem["What is 25% of 200?"]["validation_status"] == "verified"

    bad_math = by_stem["Calculate 20% of 150."]
    assert bad_math["validation_status"] == "needs_review"
    assert len(bad_math["validation_warnings"]) >= 1

    equiv_q = by_stem["Which fraction equals half of a whole?"]
    assert equiv_q["validation_status"] == "needs_review"
    assert any("equivalent" in w.lower() for w in equiv_q["validation_warnings"])

    with session_factory() as db:
        runs = db.execute(
            select(AIGenerationRun).where(
                AIGenerationRun.document_id == uuid.UUID(doc_id),
                AIGenerationRun.stage == "question_generation",
            )
        ).scalars().all()
        assert len(runs) == 1
        assert runs[0].validation_status == "valid"


# ---------------------------------------------------------------------------
# 2. PYQ Import (JSON + CSV), provenance safety, and near-duplicate skipping
# ---------------------------------------------------------------------------


def test_pyq_import_preserves_metadata_quarantines_user_supplied_and_skips_near_dups(
    m5_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, _, _ = m5_env

    # JSON import with user_supplied keys + shared passage_text
    json_payload = {
        "default_subject_code": "general_awareness",
        "answer_key_provenance": "user_supplied",
        "items": [
            {
                "question_text": "Who was the chairman of the Drafting Committee?",
                "options": [
                    {"key": "A", "text": "B. R. Ambedkar"},
                    {"key": "B", "text": "Rajendra Prasad"},
                    {"key": "C", "text": "Jawaharlal Nehru"},
                    {"key": "D", "text": "Sardar Patel"},
                ],
                "correct_option_key": "A",
                "explanation": "Dr. B. R. Ambedkar chaired the Drafting Committee.",
                "topic_name": "Indian Polity",
                "difficulty": "easy",
                "pyq_metadata": {"year": 2022, "shift": "Shift 2", "tier": "Tier 1"},
                "passage_text": "Constituent Assembly formed several key committees in 1947.",
            },
            {
                "question_text": (
                    "In which year did the Constituent Assembly adopt the Constitution?"
                ),
                "options": [
                    {"key": "A", "text": "1947"},
                    {"key": "B", "text": "1948"},
                    {"key": "C", "text": "1949"},
                    {"key": "D", "text": "1950"},
                ],
                "correct_option_key": "C",
                "topic_name": "Indian Polity",
                "difficulty": "medium",
                "pyq_metadata": {"year": 2022, "shift": "Shift 2", "tier": "Tier 1"},
                "passage_text": "Constituent Assembly formed several key committees in 1947.",
            },
        ],
    }

    r1 = client.post("/api/v1/questions/import", json=json_payload, headers=AUTH_A)
    assert r1.status_code == 201, r1.text
    b1 = r1.json()
    assert b1["imported_count"] == 2
    # user_supplied GK keys must NOT be blindly marked verified without confirmation
    assert b1["verified_count"] == 0
    assert b1["needs_review_count"] == 2
    assert b1["duplicates_skipped"] == 0

    q1, q2 = b1["items"]
    assert q1["answer_key_provenance"] == "user_supplied"
    assert q1["pyq_metadata_json"]["year"] == 2022
    assert q1["passage_group_id"] is not None
    assert q1["passage_group_id"] == q2["passage_group_id"]
    assert "Constituent Assembly" in (q1["passage_text"] or "")

    # Near-duplicate stem in second CSV import -> skipped!
    csv_text = (
        "question_text,option_a,option_b,option_c,option_d,correct_option_key,"
        "subject_code,topic_name,difficulty,year,shift\n"
        '"Who was the chairman of the Drafting Committee ?",B. R. Ambedkar,Rajendra Prasad,'
        "Jawaharlal Nehru,Sardar Patel,A,general_awareness,Indian Polity,easy,2022,Shift 2\n"
        '"Which Article guarantees equality before the law?",Article 14,Article 17,'
        "Article 19,Article 21,A,general_awareness,Indian Polity,easy,2023,Shift 1\n"
    )
    r2 = client.post(
        "/api/v1/questions/import",
        json={"answer_key_provenance": "source_answer_key", "csv_content": csv_text},
        headers=AUTH_A,
    )
    assert r2.status_code == 201, r2.text
    b2 = r2.json()
    assert b2["duplicates_skipped"] == 1
    assert b2["imported_count"] == 1
    assert b2["items"][0]["answer_key_provenance"] == "source_answer_key"
    assert b2["items"][0]["pyq_metadata_json"]["year"] == 2023


# ---------------------------------------------------------------------------
# 3 & 4. Filters, detail, PATCH manual provenance, DELETE snapshot, no leaks, 403
# ---------------------------------------------------------------------------


def test_question_bank_filters_patch_delete_answer_safety_and_403_isolation(
    m5_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, mock_provider, session_factory = m5_env
    doc_id, topic_id = _seed_doc_with_knowledge(client, session_factory)

    # Seed 1 document-backed generated question
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "questions": [
                    {
                        "question_text": "What is 10% of 500?",
                        "difficulty": "medium",
                        "topic_name": "Percentages",
                        "options": [
                            {"key": "A", "text": "40"},
                            {"key": "B", "text": "50"},
                            {"key": "C", "text": "60"},
                            {"key": "D", "text": "75"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "10% of 500 = 50.",
                        "source_page_number": 1,
                        "supporting_excerpt": "25% of 200 equals 50",
                    }
                ]
            }
        ),
        prompt_name="question_generate",
    )
    gen_resp = client.post(
        "/api/v1/questions/generate",
        json={"document_id": doc_id, "topic_id": topic_id, "count": 1},
        headers=AUTH_A,
    )
    assert gen_resp.status_code == 201
    gen_q_id = gen_resp.json()["created"][0]["id"]

    # Seed 1 standalone imported PYQ question (2024, hard)
    imp_resp = client.post(
        "/api/v1/questions/import",
        json={
            "default_subject_code": "general_awareness",
            "answer_key_provenance": "user_supplied",
            "items": [
                {
                    "question_text": "Which Schedule of the Constitution lists official languages?",
                    "options": [
                        {"key": "A", "text": "Sixth Schedule"},
                        {"key": "B", "text": "Seventh Schedule"},
                        {"key": "C", "text": "Eighth Schedule"},
                        {"key": "D", "text": "Ninth Schedule"},
                    ],
                    "correct_option_key": "B",  # intentionally wrong, to be patched to C
                    "difficulty": "hard",
                    "topic_name": "Polity",
                    "pyq_metadata": {"year": 2024, "shift": "Shift 3"},
                }
            ],
        },
        headers=AUTH_A,
    )
    assert imp_resp.status_code == 201
    imp_q_id = imp_resp.json()["items"][0]["id"]

    # Answer-key safety on list endpoint: NO correct_answer_data, NO is_correct on options
    list_resp = client.get("/api/v1/questions", headers=AUTH_A)
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["total"] == 2
    for item in list_body["items"]:
        assert "correct_answer_data" not in item
        for opt in item["options"]:
            assert "is_correct" not in opt

    # Filter checks
    assert (
        client.get(
            "/api/v1/questions",
            params={"subject_code": "quantitative_aptitude", "topic_id": topic_id},
            headers=AUTH_A,
        ).json()["total"]
        == 1
    )
    assert (
        client.get(
            "/api/v1/questions",
            params={"origin": "generated", "validation_status": "verified"},
            headers=AUTH_A,
        ).json()["total"]
        == 1
    )
    assert (
        client.get(
            "/api/v1/questions",
            params={"difficulty": "hard", "pyq_year": 2024, "q": "Schedule"},
            headers=AUTH_A,
        ).json()["total"]
        == 1
    )

    # Detail review endpoint returns explanation, correct_answer_data, and validation_warnings
    detail = client.get(f"/api/v1/questions/{imp_q_id}", headers=AUTH_A).json()
    assert detail["correct_answer_data"]["correct_option_key"] == "B"
    assert len(detail["validation_warnings"]) >= 1

    # PATCH sets answer_key_provenance='manual' when correct_option_key is edited
    patched = client.patch(
        f"/api/v1/questions/{imp_q_id}",
        json={
            "correct_option_key": "C",
            "explanation": "Eighth Schedule lists 22 recognized languages.",
            "validation_status": "verified",
        },
        headers=AUTH_A,
    )
    assert patched.status_code == 200, patched.text
    p_body = patched.json()
    assert p_body["answer_key_provenance"] == "manual"
    assert p_body["correct_option_key"] == "C"
    assert p_body["validation_status"] == "verified"

    # Cross-user 403 isolation
    assert client.get(f"/api/v1/questions/{gen_q_id}", headers=AUTH_B).status_code == 403
    assert (
        client.patch(
            f"/api/v1/questions/{gen_q_id}", json={"difficulty": "hard"}, headers=AUTH_B
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/questions/{gen_q_id}", headers=AUTH_B).status_code == 403
    assert client.get(f"/api/v1/documents/{doc_id}/questions", headers=AUTH_B).status_code == 403
    assert (
        client.post(
            "/api/v1/questions/generate",
            json={"document_id": doc_id, "count": 1},
            headers=AUTH_B,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/questions/import",
            json={
                "document_id": doc_id,
                "items": [
                    {
                        "question_text": "Foreign import test?",
                        "options": [
                            {"key": "A", "text": "1"},
                            {"key": "B", "text": "2"},
                            {"key": "C", "text": "3"},
                            {"key": "D", "text": "4"},
                        ],
                    }
                ],
            },
            headers=AUTH_B,
        ).status_code
        == 403
    )
    assert client.get("/api/v1/questions", headers=AUTH_B).json()["total"] == 0

    # Attach gen_q_id to a TestQuestion snapshot, then DELETE /questions/{id}
    with session_factory() as db:
        test_row = TestModel(
            user_id=uuid.UUID(USER_A),
            title="Snapshot Test",
            total_questions=1,
        )
        db.add(test_row)
        db.flush()
        tq = TestQuestionModel(
            test_id=test_row.id,
            question_id=uuid.UUID(gen_q_id),
            display_order=0,
            question_snapshot_json={"question_text": "What is 10% of 500?"},
        )
        db.add(tq)
        db.commit()
        tq_id = tq.id

    del_resp = client.delete(f"/api/v1/questions/{gen_q_id}", headers=AUTH_A)
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted_id"] == gen_q_id
    assert client.get(f"/api/v1/questions/{gen_q_id}", headers=AUTH_A).status_code == 404

    with session_factory() as db:
        preserved = db.get(TestQuestionModel, tq_id)
        assert preserved is not None
        assert preserved.question_id is None
        assert preserved.question_snapshot_json["question_text"] == "What is 10% of 500?"


def test_create_exam_config_pack_and_duplicate_409(
    m5_env: tuple[TestClient, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, _, _ = m5_env
    payload = {
        "exam_code": "ssc_cgl_tier_1_custom",
        "name": "SSC CGL Tier 1 Custom",
        "version": "1.0",
        "config_json": {"total_questions": 100, "duration_minutes": 60},
    }
    r1 = client.post("/api/v1/exam-configs", json=payload, headers=AUTH_A)
    assert r1.status_code == 201, r1.text
    assert r1.json()["exam_code"] == "ssc_cgl_tier_1_custom"

    r2 = client.post("/api/v1/exam-configs", json=payload, headers=AUTH_A)
    assert r2.status_code == 409
