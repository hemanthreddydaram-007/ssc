from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import AIConfigurationError, AIProviderError, LLMProvider, get_llm_provider
from app.core.security import CurrentUser, get_current_user
from app.db.base import utcnow
from app.db.session import get_db
from app.models.document import Document, ProcessingJob
from app.models.learning import Note, Topic
from app.repositories.document_repo import DocumentRepository
from app.repositories.job_repo import JobRepository, _job_to_out
from app.repositories.notes_repo import NotesRepository
from app.schemas.job import ProcessingJobOut
from app.schemas.notes import (
    GenerateNotesRequest,
    NoteDetailOut,
    NoteListResponse,
    NoteSummaryOut,
    NoteUpdateRequest,
    PYQPatternsOut,
    RegenerateNoteRequest,
)
from app.services.notes.generator import _make_note_stages, run_note_generation_in_session
from app.services.notes.pyq_analyzer import analyze_pyq_patterns
from app.services.notes.regenerator import NoteRegenerator

router = APIRouter(tags=["notes"])


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


def _note_to_detail(note: Note, topic_name: str | None) -> NoteDetailOut:
    concept_ids = []
    for cid in note.source_concept_ids_json or []:
        try:
            concept_ids.append(UUID(str(cid)))
        except ValueError:
            continue
    fact_ids = []
    for fid in note.source_fact_ids_json or []:
        try:
            fact_ids.append(UUID(str(fid)))
        except ValueError:
            continue

    return NoteDetailOut(
        id=note.id,
        document_id=note.document_id,
        topic_id=note.topic_id,
        topic_name=topic_name,
        subject_code=note.subject_code,
        note_type=note.note_type,
        title=note.title,
        content_json=note.content_json or {},
        source_concept_ids=concept_ids,
        source_fact_ids=fact_ids,
        generation_version=note.generation_version,
        status=note.status,
        model_name=note.model_name,
        prompt_name=note.prompt_name,
        prompt_version=note.prompt_version,
        understood_at=note.understood_at,
        error_message=note.error_message,
        created_at=note.created_at,
    )


def _note_to_summary(note: Note, topic_name: str | None) -> NoteSummaryOut:
    return NoteSummaryOut(
        id=note.id,
        document_id=note.document_id,
        topic_id=note.topic_id,
        topic_name=topic_name,
        subject_code=note.subject_code,
        note_type=note.note_type,
        title=note.title,
        generation_version=note.generation_version,
        status=note.status,
        model_name=note.model_name,
        prompt_name=note.prompt_name,
        prompt_version=note.prompt_version,
        understood_at=note.understood_at,
        created_at=note.created_at,
    )


@router.post(
    "/documents/{document_id}/generate-notes",
    response_model=ProcessingJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_document_notes(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    payload: GenerateNotesRequest = Body(default_factory=GenerateNotesRequest),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> ProcessingJobOut:
    """Enqueue smart note, quick revision, formula, and strategy generation from stored records."""
    document = _get_owned_document(db, document_id=document_id, user_id=current_user.id)
    repo = NotesRepository(db)
    if repo.count_knowledge_records(document.id) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no extracted facts or concepts yet. Run extract-knowledge first.",
        )

    topic_count = (
        len(payload.topic_ids)
        if payload.topic_ids is not None
        else max(1, len(repo.list_document_topic_ids_with_knowledge(document.id)))
    )
    total_items = topic_count * len(payload.note_types)

    job = JobRepository(db).create_job(
        ProcessingJob(
            document_id=document.id,
            triggered_by_user_id=current_user.id,
            job_type="generate_notes",
            status="queued",
            current_stage="queued",
            stage_details_json=_make_note_stages(),
            processed_items=0,
            total_items=total_items,
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
        run_note_generation_in_session,
        session_factory=session_factory,
        document_id=document.id,
        job_id=job.id,
        llm_provider=llm_provider,
        note_types=list(payload.note_types),
        topic_ids=payload.topic_ids,
        force_regenerate=payload.force_regenerate,
    )
    return _job_to_out(job)


@router.get("/documents/{document_id}/notes", response_model=NoteListResponse)
def list_document_notes(
    document_id: UUID,
    note_type: str | None = Query(default=None),
    topic_id: UUID | None = Query(default=None),
    subject_code: str | None = Query(default=None),
    note_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteListResponse:
    """List notes generated for a specific owned document."""
    _get_owned_document(db, document_id=document_id, user_id=current_user.id)
    rows, total = NotesRepository(db).list_notes(
        user_id=current_user.id,
        document_id=document_id,
        note_type=note_type,
        topic_id=topic_id,
        subject_code=subject_code,
        status=note_status,
        q=q,
        limit=limit,
        offset=offset,
    )
    return NoteListResponse(items=[_note_to_summary(n, tname) for n, tname in rows], total=total)


@router.get("/notes", response_model=NoteListResponse)
def list_notes(
    document_id: UUID | None = Query(default=None),
    note_type: str | None = Query(default=None),
    topic_id: UUID | None = Query(default=None),
    subject_code: str | None = Query(default=None),
    note_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteListResponse:
    """List all notes across the current user's documents."""
    if document_id is not None:
        _get_owned_document(db, document_id=document_id, user_id=current_user.id)
    rows, total = NotesRepository(db).list_notes(
        user_id=current_user.id,
        document_id=document_id,
        note_type=note_type,
        topic_id=topic_id,
        subject_code=subject_code,
        status=note_status,
        q=q,
        limit=limit,
        offset=offset,
    )
    return NoteListResponse(items=[_note_to_summary(n, tname) for n, tname in rows], total=total)


@router.get("/notes/{note_id}", response_model=NoteDetailOut)
def get_note(
    note_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteDetailOut:
    """Fetch full structured content and provenance for a single owned note."""
    found = NotesRepository(db).get_note_with_owner(note_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    note, document, topic_name = found
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this note",
        )
    return _note_to_detail(note, topic_name)


@router.post("/notes/{note_id}/regenerate", response_model=NoteDetailOut)
def regenerate_note(
    note_id: UUID,
    payload: RegenerateNoteRequest = Body(default_factory=RegenerateNoteRequest),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> NoteDetailOut:
    """Regenerate a single note or selected sections from stored knowledge records."""
    found = NotesRepository(db).get_note_with_owner(note_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    note, document, topic_name = found
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this note",
        )

    try:
        updated = NoteRegenerator(db, llm_provider).regenerate_note(
            note,
            document,
            section_keys=payload.section_keys,
            custom_instruction=payload.custom_instruction,
        )
    except (AIConfigurationError, AIProviderError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if updated.topic_id is not None and topic_name is None:
        topic = db.get(Topic, updated.topic_id)
        topic_name = topic.name if topic else None
    return _note_to_detail(updated, topic_name)


@router.patch("/notes/{note_id}", response_model=NoteDetailOut)
def update_note(
    note_id: UUID,
    payload: NoteUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteDetailOut:
    """Update note review status or mark a note as understood."""
    found = NotesRepository(db).get_note_with_owner(note_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    note, document, topic_name = found
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this note",
        )

    if payload.understood is True:
        note.understood_at = utcnow()
    elif payload.understood is False:
        note.understood_at = None

    if payload.status is not None:
        note.status = payload.status

    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_to_detail(note, topic_name)


@router.get("/documents/{document_id}/pyq-patterns", response_model=PYQPatternsOut)
def get_document_pyq_patterns(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PYQPatternsOut:
    """Return sample-scoped PYQ frequency and pattern statistics with denominators."""
    _get_owned_document(db, document_id=document_id, user_id=current_user.id)
    return analyze_pyq_patterns(db, document_id)
