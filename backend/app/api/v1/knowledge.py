from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import LLMProvider, get_llm_provider
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.document import Document, ProcessingJob
from app.repositories.document_repo import DocumentRepository
from app.repositories.job_repo import JobRepository, _job_to_out
from app.repositories.knowledge_repo import KnowledgeRepository
from app.schemas.document import DocumentOut
from app.schemas.job import ProcessingJobOut
from app.schemas.knowledge import (
    ClassificationOverrideRequest,
    ConceptOut,
    DocumentKnowledgeOut,
    ExtractKnowledgeRequest,
    FactOut,
    FactUpdateRequest,
)
from app.services.knowledge.deduplicator import compute_canonical_hash, normalize_for_hash
from app.services.knowledge.extractor import (
    _make_knowledge_stages,
    run_knowledge_extraction_in_session,
)

router = APIRouter(tags=["knowledge"])


def _get_owned_document(db: Session, *, document_id: UUID, user_id: UUID) -> Document:
    doc = DocumentRepository(db).get_by_id(document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document",
        )
    return doc


@router.post(
    "/documents/{document_id}/extract-knowledge",
    response_model=ProcessingJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def extract_document_knowledge(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    payload: ExtractKnowledgeRequest = Body(default_factory=ExtractKnowledgeRequest),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> ProcessingJobOut:
    """Enqueue AI classification and structured knowledge extraction for an extracted document."""
    document = _get_owned_document(db, document_id=document_id, user_id=current_user.id)
    repo = KnowledgeRepository(db)
    pages = repo.get_document_pages(document.id)
    chunks = repo.get_document_chunks(document.id)

    if not pages or not chunks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document must have extracted pages and chunks before knowledge extraction.",
        )

    job = JobRepository(db).create_job(
        ProcessingJob(
            document_id=document.id,
            triggered_by_user_id=current_user.id,
            job_type="extract_knowledge",
            status="queued",
            current_stage="queued",
            stage_details_json=_make_knowledge_stages(),
            processed_items=0,
            total_items=len(chunks),
            progress_percent=0,
        )
    )

    session_factory = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    background_tasks.add_task(
        run_knowledge_extraction_in_session,
        session_factory=session_factory,
        document_id=document.id,
        job_id=job.id,
        llm_provider=llm_provider,
        force_reprocess=payload.force_reprocess,
    )
    return _job_to_out(job)


@router.patch("/documents/{document_id}/classification", response_model=DocumentOut)
def override_document_classification(
    document_id: UUID,
    payload: ClassificationOverrideRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    """Allow the user to override auto-detected subject, material type, or language."""
    document = _get_owned_document(db, document_id=document_id, user_id=current_user.id)

    if payload.subject_code is not None:
        document.subject_code = payload.subject_code
    if payload.material_type is not None:
        document.material_type = payload.material_type
    if payload.language is not None:
        document.language = payload.language

    saved = DocumentRepository(db).save(document)
    return DocumentOut.model_validate(saved)


@router.get("/documents/{document_id}/knowledge", response_model=DocumentKnowledgeOut)
def get_document_knowledge(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentKnowledgeOut:
    """Return structured topics, concepts, facts, and uncertainty counts for a document."""
    document = _get_owned_document(db, document_id=document_id, user_id=current_user.id)
    repo = KnowledgeRepository(db)

    topics = repo.list_topics_for_document(document.id)
    concepts = repo.list_concepts_for_document(document.id)
    facts = repo.list_facts_for_document(document.id)

    uncertain_statuses = {"needs_review", "conflict", "rejected"}
    rejected_or_uncertain = sum(1 for f in facts if f.review_status in uncertain_statuses) + sum(
        1 for c in concepts if c.review_status in uncertain_statuses
    )

    return DocumentKnowledgeOut(
        document_id=document.id,
        subject_code=document.subject_code,
        detected_subject_code=document.detected_subject_code,
        classification_confidence=document.classification_confidence,
        topics=topics,
        concepts=[ConceptOut.model_validate(c) for c in concepts],
        facts=[FactOut.model_validate(f) for f in facts],
        rejected_or_uncertain_count=rejected_or_uncertain,
    )


@router.patch("/facts/{fact_id}", response_model=FactOut)
def update_fact(
    fact_id: UUID,
    payload: FactUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FactOut:
    """Manually correct a fact's text, type, or review status with ownership enforcement."""
    repo = KnowledgeRepository(db)
    found = repo.get_fact_with_owner(fact_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    fact, document = found
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this fact",
        )

    if payload.content is not None:
        fact.content = payload.content
    if payload.fact_type is not None:
        fact.fact_type = payload.fact_type
    if payload.review_status is not None:
        fact.review_status = payload.review_status

    fact.canonical_hash = compute_canonical_hash(
        str(fact.document_id),
        str(fact.topic_id or ""),
        fact.fact_type,
        normalize_for_hash(fact.content),
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return FactOut.model_validate(fact)
