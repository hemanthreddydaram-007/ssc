from __future__ import annotations

import json
from collections.abc import Generator
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.api.v1.questions import router as questions_router
from app.core.config import Settings
from app.db.seed import seed_defaults
from app.db.session import get_db
from app.models.document import Document
from app.models.learning import Concept, Fact, Topic
from app.models.user import User


def _build_client(db_session: Session, mock_llm: MockLLMProvider) -> TestClient:
    app = FastAPI()
    app.include_router(questions_router, prefix="/api/v1")

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm
    return TestClient(app)


def _seed_doc_and_knowledge(db_session: Session, user_id: UUID) -> tuple[Document, Topic, Concept]:
    doc = Document(
        user_id=user_id,
        title="Maths Percentages Notes",
        original_filename="percentages.pdf",
        source_type="pdf",
        mime_type="application/pdf",
        file_size_bytes=2048,
        sha256="a" * 64,
        storage_key=f"users/{user_id}/documents/percentages.pdf",
        subject_code="quantitative_aptitude",
        material_type="notes",
        language="en",
        page_count=2,
        status="extracted",
    )
    db_session.add(doc)
    db_session.flush()

    topic = Topic(
        subject_code="quantitative_aptitude",
        name="Percentages",
        slug="percentages-gen",
    )
    db_session.add(topic)
    db_session.flush()

    concept = Concept(
        document_id=doc.id,
        topic_id=topic.id,
        title="Percentage of a Quantity",
        explanation="x% of y equals (x / 100) * y.",
        difficulty="easy",
        provenance="extracted",
        confidence=0.95,
        review_status="verified",
        source_refs_json=[{"page_number": 1, "supporting_excerpt": "x% of y = (x/100)*y"}],
    )
    fact = Fact(
        document_id=doc.id,
        topic_id=topic.id,
        fact_type="formula",
        content="20% of 250 = 50",
        provenance="extracted",
        confidence=0.95,
        source_page_number=1,
        supporting_excerpt="20% of 250 = 50",
        review_status="verified",
    )
    db_session.add(concept)
    db_session.add(fact)
    db_session.commit()
    db_session.refresh(doc)
    db_session.refresh(topic)
    db_session.refresh(concept)
    return doc, topic, concept


def test_generate_questions_validates_math_dedups_and_quarantines(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    doc, topic, _ = _seed_doc_and_knowledge(db_session, test_settings.local_default_user_id)

    mock_llm = MockLLMProvider()
    mock_llm.register_handler(
        "question_generate",
        lambda _p: json.dumps(
            {
                "questions": [
                    {
                        "question_text": "What is 20% of 250?",
                        "difficulty": "easy",
                        "topic_name": "Percentages",
                        "options": [
                            {"key": "A", "text": "40"},
                            {"key": "B", "text": "50"},
                            {"key": "C", "text": "60"},
                            {"key": "D", "text": "75"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "20% of 250 = 50.",
                        "source_page_number": 1,
                        "supporting_excerpt": "20% of 250 = 50",
                    },
                    {
                        "question_text": "What is 20% of 250?",
                        "difficulty": "easy",
                        "topic_name": "Percentages",
                        "options": [
                            {"key": "A", "text": "40"},
                            {"key": "B", "text": "50"},
                            {"key": "C", "text": "60"},
                            {"key": "D", "text": "75"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "Duplicate stem.",
                    },
                    {
                        "question_text": "What is 10% of 300?",
                        "difficulty": "easy",
                        "topic_name": "Percentages",
                        "options": [
                            {"key": "A", "text": "20"},
                            {"key": "B", "text": "30"},
                            {"key": "C", "text": "40"},
                            {"key": "D", "text": "50"},
                        ],
                        "correct_option_key": "A",
                        "explanation": "10% of 300 = 20.",
                        "source_page_number": 1,
                    },
                ]
            }
        ),
    )

    with _build_client(db_session, mock_llm) as client:
        resp = client.post(
            "/api/v1/questions/generate",
            json={"document_id": str(doc.id), "topic_id": str(topic.id), "count": 5},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["verified_count"] == 1
        assert data["needs_review_count"] == 1
        assert data["duplicates_skipped"] == 1
        assert len(data["created"]) == 2
        q_ok = next(q for q in data["created"] if "20% of 250" in q["question_text"])
        q_bad = next(q for q in data["created"] if "10% of 300" in q["question_text"])
        assert q_ok["validation_status"] == "verified"
        assert q_ok["answer_key_provenance"] == "deterministic_solver"
        assert q_bad["validation_status"] == "needs_review"
        assert q_bad["answer_key_provenance"] == "conflicting"
        assert len(q_bad["validation_warnings"]) >= 1


def test_import_csv_and_json_detail_patch_delete_and_ownership(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    other_id = UUID("00000000-0000-0000-0000-000000000088")
    db_session.add(User(id=other_id, display_name="Other"))
    db_session.commit()

    mock_llm = MockLLMProvider()
    with _build_client(db_session, mock_llm) as client:
        # 1. JSON import with user_supplied provenance -> stays needs_review for non-math
        json_resp = client.post(
            "/api/v1/questions/import",
            json={
                "default_subject_code": "general_awareness",
                "answer_key_provenance": "user_supplied",
                "items": [
                    {
                        "question_text": "Which Article abolishes untouchability?",
                        "options": [
                            {"key": "A", "text": "Article 14"},
                            {"key": "B", "text": "Article 17"},
                            {"key": "C", "text": "Article 19"},
                            {"key": "D", "text": "Article 21"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "Article 17 abolishes untouchability.",
                        "pyq_metadata": {"year": 2022, "shift": "Shift 2"},
                    }
                ],
            },
        )
        assert json_resp.status_code == 201, json_resp.text
        imported = json_resp.json()
        assert imported["imported_count"] == 1
        assert imported["needs_review_count"] == 1
        q_id = imported["items"][0]["id"]

        # 2. CSV import with pyq_year and duplicate check
        csv_text = (
            "question_text,option_a,option_b,option_c,option_d,"
            "correct_option_key,year,subject_code\n"
            '"What is 50% of 100?",25,50,75,100,B,2023,quantitative_aptitude\n'
            '"Which Article abolishes untouchability?",'
            "Article 14,Article 17,Article 19,Article 21,B,2022,general_awareness\n"
        )
        csv_resp = client.post(
            "/api/v1/questions/import",
            json={"answer_key_provenance": "source_answer_key", "csv_content": csv_text},
        )
        assert csv_resp.status_code == 201, csv_resp.text
        csv_data = csv_resp.json()
        assert csv_data["imported_count"] == 1
        assert csv_data["duplicates_skipped"] == 1
        assert csv_data["verified_count"] == 1

        # 3. Filter by pyq_year
        filtered = client.get("/api/v1/questions", params={"pyq_year": 2023})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert "50% of 100" in filtered.json()["items"][0]["question_text"]

        # 4. Detail endpoint & ownership check
        detail = client.get(f"/api/v1/questions/{q_id}")
        assert detail.status_code == 200
        assert detail.json()["correct_answer_data"]["correct_option_key"] == "B"
        assert "owner_user_id" not in detail.json()["correct_answer_data"]

        forbidden = client.get(
            f"/api/v1/questions/{q_id}", headers={"X-User-Id": str(other_id)}
        )
        assert forbidden.status_code == 403

        # 5. PATCH updates key -> provenance becomes manual, can verify
        patched = client.patch(
            f"/api/v1/questions/{q_id}",
            json={"correct_option_key": "B", "validation_status": "verified"},
        )
        assert patched.status_code == 200
        assert patched.json()["answer_key_provenance"] == "manual"
        assert patched.json()["validation_status"] == "verified"

        # 6. DELETE removes question
        deleted = client.delete(f"/api/v1/questions/{q_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted_id"] == q_id
        assert client.get(f"/api/v1/questions/{q_id}").status_code == 404
