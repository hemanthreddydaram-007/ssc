from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.mock_provider import MockLLMProvider
from app.models.document import Document, DocumentChunk, DocumentPage, ProcessingJob
from app.models.learning import AIGenerationRun, Concept, Fact, Topic
from app.models.user import User
from app.repositories.knowledge_repo import KnowledgeRepository
from app.services.knowledge.deduplicator import upsert_fact
from app.services.knowledge.extractor import KnowledgeExtractionPipeline


def _seed_extracted_document(db: Session) -> tuple[User, Document]:
    user = User(id=uuid.uuid4(), display_name="SSC Aspirant")
    db.add(user)
    db.flush()

    doc = Document(
        id=uuid.uuid4(),
        user_id=user.id,
        title="SSC CHSL Maths & PYQ Pack",
        original_filename="maths_pyq.pdf",
        source_type="pdf",
        mime_type="application/pdf",
        file_size_bytes=4096,
        sha256="b" * 64,
        storage_key="users/u/doc/maths_pyq.pdf",
        material_type="pyq_paper",
        language="en",
        page_count=2,
        status="extracted",
    )
    db.add(doc)
    db.flush()

    p1_text = (
        "Percentages Formula: Profit Percentage = (Profit / Cost Price) * 100.\n"
        "Q.1 If cost price is Rs 200 and selling price is Rs 250, find profit percentage?\n"
        "(A) 20% (B) 25% (C) 30% (D) 15%\nAnswer: B"
    )
    p2_text = "Time and Work: If A finishes work in 10 days, one day work = 1/10."

    db.add_all(
        [
            DocumentPage(
                document_id=doc.id,
                page_number=1,
                extracted_text=p1_text,
                extraction_method="pymupdf",
                confidence=1.0,
                processing_status="done",
                raw_char_count=len(p1_text),
            ),
            DocumentPage(
                document_id=doc.id,
                page_number=2,
                extracted_text=p2_text,
                extraction_method="pymupdf",
                confidence=1.0,
                processing_status="done",
                raw_char_count=len(p2_text),
            ),
            DocumentChunk(
                document_id=doc.id,
                chunk_index=0,
                page_start=1,
                page_end=1,
                section_title="Percentages",
                chunk_type="question_block",
                content_text=p1_text,
                token_estimate=40,
            ),
            DocumentChunk(
                document_id=doc.id,
                chunk_index=1,
                page_start=2,
                page_end=2,
                section_title="Time and Work",
                chunk_type="prose",
                content_text=p2_text,
                token_estimate=20,
            ),
        ]
    )
    db.commit()
    return user, doc


def test_deduplicator_merges_exact_facts_and_flags_conflicting_values(db_session: Session) -> None:
    _, doc = _seed_extracted_document(db_session)
    repo = KnowledgeRepository(db_session)
    topic = Topic(subject_code="general_awareness", name="Indian History", slug="indian-history")
    db_session.add(topic)
    db_session.flush()

    f1 = upsert_fact(
        repo,
        document_id=doc.id,
        topic_id=topic.id,
        chunk_id=None,
        fact_type="date",
        content="The Battle of Plassey was fought in 1757.",
        provenance="extracted",
        confidence=0.9,
        source_page_number=1,
        supporting_excerpt="Battle of Plassey was fought in 1757",
        is_time_sensitive=False,
        source_date_label=None,
        review_status="verified",
        model_name="mock",
        prompt_name="knowledge_extraction",
        prompt_version="v1",
        generation_run_id=None,
    )

    # Identical fact on page 2 -> merged into f1 without new row
    f1_dup = upsert_fact(
        repo,
        document_id=doc.id,
        topic_id=topic.id,
        chunk_id=None,
        fact_type="date",
        content="The Battle of Plassey was fought in 1757",
        provenance="extracted",
        confidence=0.92,
        source_page_number=2,
        supporting_excerpt="Battle of Plassey was fought in 1757",
        is_time_sensitive=False,
        source_date_label=None,
        review_status="verified",
        model_name="mock",
        prompt_name="knowledge_extraction",
        prompt_version="v1",
        generation_run_id=None,
    )
    assert f1_dup.id == f1.id
    assert len(f1_dup.source_refs_json) == 2

    # Conflicting date -> NEVER merged; both kept and marked conflict with shared conflict_group_id
    f_conflict = upsert_fact(
        repo,
        document_id=doc.id,
        topic_id=topic.id,
        chunk_id=None,
        fact_type="date",
        content="The Battle of Plassey was fought in 1764.",
        provenance="extracted",
        confidence=0.85,
        source_page_number=2,
        supporting_excerpt="Battle of Plassey was fought in 1764",
        is_time_sensitive=False,
        source_date_label=None,
        review_status="verified",
        model_name="mock",
        prompt_name="knowledge_extraction",
        prompt_version="v1",
        generation_run_id=None,
    )

    db_session.refresh(f1)
    assert f_conflict.id != f1.id
    assert f1.review_status == "conflict"
    assert f_conflict.review_status == "conflict"
    assert f1.conflict_group_id is not None
    assert f1.conflict_group_id == f_conflict.conflict_group_id


def test_knowledge_extraction_pipeline_persists_grounded_records_and_is_idempotent(
    db_session: Session,
) -> None:
    user, doc = _seed_extracted_document(db_session)
    job = ProcessingJob(
        document_id=doc.id,
        triggered_by_user_id=user.id,
        job_type="extract_knowledge",
        status="queued",
        current_stage="queued",
    )
    db_session.add(job)
    db_session.commit()

    captured_candidates: list[object] = []

    class _FakeIngestionService:
        def __init__(self, db: Session) -> None:
            self.db = db

        def ingest_candidates(self, *, document_id, candidates, topic_id_map=None):
            captured_candidates.extend(candidates)
            return type("Summary", (), {"inserted_count": len(candidates)})()

    provider = MockLLMProvider()
    with patch(
        "app.services.question_generation.ingestion.QuestionIngestionService",
        _FakeIngestionService,
        create=True,
    ):
        pipeline = KnowledgeExtractionPipeline(llm_provider=provider)
        pipeline.run(db_session, doc, job, force_reprocess=False)

    db_session.refresh(doc)
    db_session.refresh(job)
    assert job.status == "completed"
    assert doc.status == "knowledge_ready"
    assert doc.detected_subject_code == "quantitative_aptitude"

    facts = list(db_session.execute(select(Fact).where(Fact.document_id == doc.id)).scalars())
    concepts = list(
        db_session.execute(select(Concept).where(Concept.document_id == doc.id)).scalars()
    )
    runs = list(
        db_session.execute(
            select(AIGenerationRun).where(AIGenerationRun.document_id == doc.id)
        ).scalars()
    )
    assert len(facts) >= 2
    assert all(f.source_page_number in (1, 2) for f in facts)
    assert all(f.model_name == "mock-gemini-2.5-flash" and f.prompt_version == "v1" for f in facts)
    assert len(concepts) >= 2
    assert len(runs) == 3  # 1 classification + 2 chunks
    assert len(captured_candidates) == 1
    assert captured_candidates[0].correct_option_key == "B"  # type: ignore[attr-defined]
    assert doc.coverage_summary_json is not None
    assert doc.coverage_summary_json["facts_extracted"] == len(facts)

    # Re-run without force_reprocess should not duplicate identical facts/concepts
    job2 = ProcessingJob(
        document_id=doc.id,
        triggered_by_user_id=user.id,
        job_type="extract_knowledge",
        status="queued",
        current_stage="queued",
    )
    db_session.add(job2)
    db_session.commit()
    with patch(
        "app.services.question_generation.ingestion.QuestionIngestionService",
        _FakeIngestionService,
        create=True,
    ):
        pipeline.run(db_session, doc, job2, force_reprocess=False)

    facts_after = list(db_session.execute(select(Fact).where(Fact.document_id == doc.id)).scalars())
    concepts_after = list(
        db_session.execute(select(Concept).where(Concept.document_id == doc.id)).scalars()
    )
    assert len(facts_after) == len(facts)
    assert len(concepts_after) == len(concepts)


def test_pipeline_skips_failed_validation_chunk_without_storing_malformed_records(
    db_session: Session,
) -> None:
    user, doc = _seed_extracted_document(db_session)
    job = ProcessingJob(
        document_id=doc.id,
        triggered_by_user_id=user.id,
        job_type="extract_knowledge",
        status="queued",
        current_stage="queued",
    )
    db_session.add(job)
    db_session.commit()

    provider = MockLLMProvider()
    # Chunk 1 fails both initial and repair attempts
    provider.enqueue_raw("not-json", prompt_name="knowledge_extraction")
    provider.enqueue_raw("still-not-json", prompt_name="knowledge_extraction:repair")

    pipeline = KnowledgeExtractionPipeline(llm_provider=provider)
    pipeline.run(db_session, doc, job, force_reprocess=False)

    db_session.refresh(job)
    assert job.status == "completed"
    runs = list(
        db_session.execute(
            select(AIGenerationRun).where(
                AIGenerationRun.document_id == doc.id,
                AIGenerationRun.validation_status == "failed_validation",
            )
        ).scalars()
    )
    assert len(runs) == 1
    # Chunk 2 still succeeded cleanly
    facts = list(db_session.execute(select(Fact).where(Fact.document_id == doc.id)).scalars())
    assert len(facts) == 1
    assert facts[0].source_page_number == 2
