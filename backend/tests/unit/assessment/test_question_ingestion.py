from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.questions import router as questions_router
from app.core.config import Settings
from app.db.seed import seed_defaults
from app.db.session import get_db
from app.models.document import Document
from app.models.learning import Topic
from app.models.user import User
from app.services.question_generation.ingestion import QuestionIngestionService


@dataclass
class _CandidateOpt:
    key: str
    text: str


@dataclass
class _CandidateQuestion:
    question_text: str
    subject_code: str
    options: list[_CandidateOpt]
    correct_option_key: str | None = None
    topic_name: str | None = None
    difficulty: str = "medium"
    explanation: str = ""
    source_page_number: int | None = 1
    supporting_excerpt: str | None = None
    answer_key_provenance: str = "source_answer_key"
    pyq_metadata: dict | None = None
    model_name: str | None = "mock-gemini"
    prompt_name: str | None = "extract_knowledge"
    prompt_version: str | None = "v1"


def _build_questions_test_client(db_session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(questions_router, prefix="/api/v1")

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _create_document(db_session: Session, user_id: UUID, title: str = "PYQ Paper") -> Document:
    doc = Document(
        user_id=user_id,
        title=title,
        original_filename="pyq.pdf",
        source_type="pdf",
        mime_type="application/pdf",
        file_size_bytes=1234,
        sha256=f"{user_id.hex[:32]}{title.encode().hex()[:32]}".ljust(64, "0")[:64],
        storage_key=f"users/{user_id}/documents/pyq.pdf",
        subject_code="quantitative_aptitude",
        material_type="previous_year_paper",
        language="en",
        page_count=2,
        status="extracted",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def test_ingest_candidates_validates_dedups_and_preserves_provenance(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    doc = _create_document(db_session, test_settings.local_default_user_id)

    topic = Topic(
        subject_code="quantitative_aptitude",
        name="Percentages",
        slug="percentages",
    )
    db_session.add(topic)
    db_session.commit()
    db_session.refresh(topic)

    candidates = [
        _CandidateQuestion(
            question_text="What is 20% of 250?",
            subject_code="quantitative_aptitude",
            topic_name="Percentages",
            difficulty="easy",
            options=[
                _CandidateOpt("A", "40"),
                _CandidateOpt("B", "50"),
                _CandidateOpt("C", "60"),
                _CandidateOpt("D", "75"),
            ],
            correct_option_key="B",
            explanation="20% of 250 equals 50.",
            source_page_number=2,
            supporting_excerpt="Q1. What is 20% of 250? (A) 40 (B) 50 (C) 60 (D) 75",
            pyq_metadata={"year": 2023, "shift": "Shift 1"},
        ),
        # Duplicate with extra whitespace/casing should be skipped
        _CandidateQuestion(
            question_text="  what   is 20%   of 250? ",
            subject_code="quantitative_aptitude",
            options=[
                _CandidateOpt("A", "40"),
                _CandidateOpt("B", "50"),
                _CandidateOpt("C", "60"),
                _CandidateOpt("D", "75"),
            ],
            correct_option_key="B",
            supporting_excerpt="Q1 duplicate",
        ),
        # Missing excerpt and duplicate option text -> needs_review
        _CandidateQuestion(
            question_text="Find x if 2x + 4 = 10.",
            subject_code="quantitative_aptitude",
            options=[
                _CandidateOpt("A", "3"),
                _CandidateOpt("B", "3"),
                _CandidateOpt("C", "4"),
                _CandidateOpt("D", "5"),
            ],
            correct_option_key="A",
            supporting_excerpt=None,
        ),
        # Missing correct option key -> needs_review + unverified provenance
        _CandidateQuestion(
            question_text="Solve 15 * 4.",
            subject_code="quantitative_aptitude",
            options=[
                _CandidateOpt("A", "50"),
                _CandidateOpt("B", "60"),
                _CandidateOpt("C", "70"),
                _CandidateOpt("D", "80"),
            ],
            correct_option_key=None,
            supporting_excerpt="Solve 15 * 4.",
        ),
    ]

    service = QuestionIngestionService(db_session)
    summary = service.ingest_candidates(
        doc.id,
        candidates,
        topic_id_map={"Percentages": topic.id},
    )

    assert summary.total_received == 4
    assert summary.inserted_count == 3
    assert summary.skipped_duplicate_count == 1
    assert summary.verified_count == 1
    assert summary.needs_review_count == 2

    # Re-ingesting the same candidate batch should skip all as duplicates
    second = service.ingest_candidates(doc.id, [candidates[0]])
    assert second.inserted_count == 0
    assert second.skipped_duplicate_count == 1


def test_questions_api_filters_and_ownership_isolation(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    user_a_doc = _create_document(db_session, test_settings.local_default_user_id, "User A Paper")

    other_user_id = UUID("00000000-0000-0000-0000-000000000077")
    db_session.add(User(id=other_user_id, display_name="Other User"))
    db_session.commit()
    user_b_doc = _create_document(db_session, other_user_id, "User B Paper")

    service = QuestionIngestionService(db_session)
    service.ingest_candidates(
        user_a_doc.id,
        [
            _CandidateQuestion(
                question_text="Synonym of 'Benevolent'?",
                subject_code="english",
                difficulty="easy",
                options=[
                    _CandidateOpt("A", "Kind"),
                    _CandidateOpt("B", "Cruel"),
                    _CandidateOpt("C", "Hostile"),
                    _CandidateOpt("D", "Greedy"),
                ],
                correct_option_key="A",
                supporting_excerpt="Synonym of Benevolent: Kind",
                source_page_number=1,
            )
        ],
    )
    service.ingest_candidates(
        user_b_doc.id,
        [
            _CandidateQuestion(
                question_text="Capital of India?",
                subject_code="general_awareness",
                difficulty="easy",
                options=[
                    _CandidateOpt("A", "Mumbai"),
                    _CandidateOpt("B", "New Delhi"),
                    _CandidateOpt("C", "Kolkata"),
                    _CandidateOpt("D", "Chennai"),
                ],
                correct_option_key="B",
                supporting_excerpt="Capital of India is New Delhi.",
                source_page_number=1,
            )
        ],
    )

    with _build_questions_test_client(db_session) as client:
        # User A sees only their own question
        resp = client.get("/api/v1/questions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["subject_code"] == "english"
        assert data["items"][0]["validation_status"] == "verified"
        assert len(data["items"][0]["options"]) == 4
        assert "is_correct" not in data["items"][0]["options"][0]

        # Filtered document endpoint for User A
        doc_resp = client.get(
            f"/api/v1/documents/{user_a_doc.id}/questions",
            params={"validation_status": "verified"},
        )
        assert doc_resp.status_code == 200
        assert doc_resp.json()["total"] == 1

        # User A cannot read User B's document questions
        forbidden_resp = client.get(f"/api/v1/documents/{user_b_doc.id}/questions")
        assert forbidden_resp.status_code == 403

        # User B sees only their own question
        user_b_resp = client.get(
            "/api/v1/questions",
            headers={"X-User-Id": str(other_user_id)},
        )
        assert user_b_resp.status_code == 200
        assert user_b_resp.json()["total"] == 1
        assert user_b_resp.json()["items"][0]["subject_code"] == "general_awareness"
