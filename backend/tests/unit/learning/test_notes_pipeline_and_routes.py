from __future__ import annotations

import uuid
from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.api.v1 import jobs, notes
from app.db.session import get_db
from app.models.assessment import Question
from app.models.document import Document, ProcessingJob
from app.models.learning import Concept, Fact, Note, Topic
from app.models.user import User
from app.repositories.knowledge_repo import KnowledgeRepository
from app.schemas.notes import NoteContentJson
from app.services.notes.generator import NoteGenerationPipeline
from app.services.notes.pyq_analyzer import analyze_pyq_patterns
from app.services.notes.regenerator import NoteRegenerator
from app.services.notes.validators import content_text_length


def _make_notes_client(db_engine: Engine, provider: MockLLMProvider) -> TestClient:
    session_factory = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    app = FastAPI()
    app.include_router(notes.router, prefix="/api/v1")
    app.include_router(jobs.router, prefix="/api/v1")

    def _override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app)


def _seed_doc_with_stored_knowledge(
    db: Session,
    *,
    user_id: uuid.UUID,
    include_knowledge: bool = True,
) -> tuple[Document, Topic, Topic]:
    if db.get(User, user_id) is None:
        db.add(User(id=user_id, display_name="Student"))
        db.flush()

    # Deliberately use a nonexistent storage_key to prove note generation never reads raw PDF
    doc = Document(
        id=uuid.uuid4(),
        user_id=user_id,
        title="SSC CHSL Maths Notes",
        original_filename="missing_on_disk.pdf",
        source_type="pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_key="nonexistent/path/never_opened.pdf",
        subject_code="quantitative_aptitude",
        material_type="pyq_paper",
        language="en",
        page_count=2,
        status="knowledge_ready",
    )
    db.add(doc)
    db.flush()

    k_repo = KnowledgeRepository(db)
    t1 = k_repo.get_or_create_topic(
        subject_code="quantitative_aptitude",
        name="Percentages",
        slug="percentages",
        is_canonical=True,
    )
    t_empty = k_repo.get_or_create_topic(
        subject_code="quantitative_aptitude",
        name="Trigonometry",
        slug="trigonometry",
        is_canonical=True,
    )
    db.flush()

    if include_knowledge:
        db.add(
            Fact(
                document_id=doc.id,
                topic_id=t1.id,
                fact_type="formula",
                content="Percentage change = ((New - Old) / Old) * 100",
                provenance="extracted",
                confidence=0.95,
                source_page_number=1,
                supporting_excerpt="Percentage change = ((New - Old) / Old) * 100",
                review_status="verified",
            )
        )
        db.add(
            Concept(
                document_id=doc.id,
                topic_id=t1.id,
                title="Fraction to Percentage Conversion",
                explanation="Multiply any fraction by 100 to express it as a percentage.",
                difficulty="easy",
                provenance="paraphrased",
                confidence=0.9,
                source_refs_json=[
                    {
                        "document_id": str(doc.id),
                        "page_number": 1,
                        "supporting_excerpt": "Multiply fraction by 100",
                    }
                ],
                review_status="verified",
            )
        )
        db.add_all(
            [
                Question(
                    document_id=doc.id,
                    topic_id=t1.id,
                    subject_code="quantitative_aptitude",
                    question_text="What is 20% of 250?",
                    question_type="single_choice",
                    difficulty="easy",
                    origin="extracted",
                    source_page_number=2,
                    supporting_excerpt="What is 20% of 250?",
                    stem_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    correct_answer_data={"option_key": "B"},
                    pyq_metadata_json={"year": 2023, "shift": "Shift 1"},
                    answer_key_provenance="source_answer_key",
                    validation_status="verified",
                ),
                Question(
                    document_id=doc.id,
                    topic_id=t1.id,
                    subject_code="quantitative_aptitude",
                    question_text="What is 15% of 400?",
                    question_type="single_choice",
                    difficulty="medium",
                    origin="extracted",
                    source_page_number=2,
                    supporting_excerpt="What is 15% of 400?",
                    stem_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    correct_answer_data={"option_key": "A"},
                    pyq_metadata_json={"year": 2023, "shift": "Shift 1"},
                    answer_key_provenance="source_answer_key",
                    validation_status="verified",
                ),
            ]
        )
    db.commit()
    return doc, t1, t_empty


def test_note_pipeline_generates_from_db_records_and_handles_empty_topic(
    db_session: Session,
) -> None:
    user_id = uuid.uuid4()
    doc, t1, t_empty = _seed_doc_with_stored_knowledge(db_session, user_id=user_id)

    job = ProcessingJob(
        document_id=doc.id,
        triggered_by_user_id=user_id,
        job_type="generate_notes",
        status="queued",
        current_stage="queued",
    )
    db_session.add(job)
    db_session.commit()

    provider = MockLLMProvider()
    pipeline = NoteGenerationPipeline(provider)
    pipeline.run(
        db_session,
        doc,
        job,
        note_types=["detailed", "quick_revision", "formula_sheet", "strategy_sheet"],
        topic_ids=[t1.id, t_empty.id],
    )

    db_session.refresh(job)
    assert job.status == "completed"

    t1_notes = list(
        db_session.execute(
            select(Note).where(Note.document_id == doc.id, Note.topic_id == t1.id)
        ).scalars()
    )
    assert {n.note_type for n in t1_notes} == {
        "detailed",
        "quick_revision",
        "formula_sheet",
        "strategy_sheet",
    }

    detailed = next(n for n in t1_notes if n.note_type == "detailed")
    quick = next(n for n in t1_notes if n.note_type == "quick_revision")
    assert content_text_length(NoteContentJson.model_validate(quick.content_json)) < (
        content_text_length(NoteContentJson.model_validate(detailed.content_json))
    )

    # Empty topic must produce insufficient_evidence without LLM hallucination
    empty_notes = list(
        db_session.execute(
            select(Note).where(Note.document_id == doc.id, Note.topic_id == t_empty.id)
        ).scalars()
    )
    assert len(empty_notes) == 4
    assert all(n.status == "insufficient_evidence" for n in empty_notes)
    assert all(
        n.content_json.get("insufficient_evidence_message") for n in empty_notes
    )
    # Only 4 LLM calls for t1 (0 for t_empty)
    assert len(provider.calls) == 4

    # Single-topic regeneration updates only the target note & increments generation_version
    regenerator = NoteRegenerator(db_session, provider)
    updated = regenerator.regenerate_note(
        detailed, doc, section_keys=["key_facts"], custom_instruction="Highlight percentage change"
    )
    assert updated.generation_version == 2
    db_session.refresh(quick)
    assert quick.generation_version == 1


def test_pyq_analyzer_reports_explicit_denominator_and_templates(db_session: Session) -> None:
    doc, _, _ = _seed_doc_with_stored_knowledge(db_session, user_id=uuid.uuid4())
    patterns = analyze_pyq_patterns(db_session, doc.id)

    assert patterns.total_questions_analyzed == 2
    assert "2 question(s)" in patterns.sample_note
    assert patterns.subjects[0].percentage == 100.0
    assert patterns.years_shifts == [{"year": "2023", "shift": "Shift 1", "count": 2}]
    assert len(patterns.repeated_templates) == 1
    assert patterns.repeated_templates[0]["denominator"] == 2


def test_notes_api_endpoints_and_ownership(
    db_engine: Engine,
    db_session: Session,
    test_settings,
) -> None:
    owner_id = test_settings.local_default_user_id
    other_id = uuid.uuid4()

    empty_doc, _, _ = _seed_doc_with_stored_knowledge(
        db_session, user_id=owner_id, include_knowledge=False
    )
    doc, t1, _ = _seed_doc_with_stored_knowledge(
        db_session, user_id=owner_id, include_knowledge=True
    )

    client = _make_notes_client(db_engine, MockLLMProvider())

    # 1. 409 when document has no extracted knowledge yet
    assert client.post(f"/api/v1/documents/{empty_doc.id}/generate-notes").status_code == 409

    # 2. Generate notes -> 202 + job completes
    gen_resp = client.post(
        f"/api/v1/documents/{doc.id}/generate-notes",
        json={"note_types": ["detailed", "quick_revision", "strategy_sheet"]},
    )
    assert gen_resp.status_code == 202
    job_id = gen_resp.json()["id"]
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "completed"

    # 3. List document notes and global notes
    doc_notes_resp = client.get(f"/api/v1/documents/{doc.id}/notes")
    assert doc_notes_resp.status_code == 200
    assert doc_notes_resp.json()["total"] == 3

    global_notes_resp = client.get("/api/v1/notes?note_type=quick_revision")
    assert global_notes_resp.status_code == 200
    assert global_notes_resp.json()["total"] == 1

    note_id = doc_notes_resp.json()["items"][0]["id"]

    # 4. Read detail, mark understood, regenerate single note
    detail_resp = client.get(f"/api/v1/notes/{note_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["generation_version"] == 1

    patch_resp = client.patch(f"/api/v1/notes/{note_id}", json={"understood": True})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["understood_at"] is not None

    regen_resp = client.post(
        f"/api/v1/notes/{note_id}/regenerate",
        json={"custom_instruction": "Make concise"},
    )
    assert regen_resp.status_code == 200
    assert regen_resp.json()["generation_version"] == 2

    # 5. PYQ patterns endpoint
    pyq_resp = client.get(f"/api/v1/documents/{doc.id}/pyq-patterns")
    assert pyq_resp.status_code == 200
    assert pyq_resp.json()["total_questions_analyzed"] == 2

    # 6. Cross-user 403 isolation
    headers_other = {"X-User-Id": str(other_id)}
    assert (
        client.get(f"/api/v1/documents/{doc.id}/notes", headers=headers_other).status_code == 403
    )
    assert client.get(f"/api/v1/notes/{note_id}", headers=headers_other).status_code == 403
    assert (
        client.post(f"/api/v1/notes/{note_id}/regenerate", headers=headers_other).status_code
        == 403
    )
    assert client.get("/api/v1/notes", headers=headers_other).json()["total"] == 0
