from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import get_llm_provider
from app.core.config import Settings, get_settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.repositories.job_repo import JobAccessDeniedError, JobNotFoundError, JobService
from app.schemas.job import JobListResponse, ProcessingJobOut
from app.services.extraction.extraction_pipeline import run_extraction_job_in_session
from app.services.knowledge.extractor import run_knowledge_extraction_in_session
from app.services.notes.generator import run_note_generation_in_session

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    """Build the processing job service."""
    return JobService(db)


@router.get("", response_model=JobListResponse)
def list_jobs(
    document_id: UUID | None = Query(default=None),
    job_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> JobListResponse:
    """List processing jobs for documents owned by the current user."""
    return service.list_jobs(
        user_id=current_user.id,
        document_id=document_id,
        status=job_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=ProcessingJobOut)
def get_job(
    job_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> ProcessingJobOut:
    """Fetch status and stage breakdown for a processing job."""
    try:
        return service.get_owned_job(job_id=job_id, user_id=current_user.id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/{job_id}/retry",
    response_model=ProcessingJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_job(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    service: JobService = Depends(get_job_service),
) -> ProcessingJobOut:
    """Create and enqueue a retry job for a previously submitted processing job."""
    try:
        new_job = service.prepare_retry_job(job_id=job_id, user_id=current_user.id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    session_factory = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    if new_job.job_type == "extract_knowledge":
        llm_provider = get_llm_provider(settings)
        background_tasks.add_task(
            run_knowledge_extraction_in_session,
            session_factory=session_factory,
            document_id=new_job.document_id,
            job_id=new_job.id,
            llm_provider=llm_provider,
            force_reprocess=True,
        )
    elif new_job.job_type == "generate_notes":
        llm_provider = get_llm_provider(settings)
        note_types, topic_ids, force_regen = service.get_retry_note_params(new_job.id)
        background_tasks.add_task(
            run_note_generation_in_session,
            session_factory=session_factory,
            document_id=new_job.document_id,
            job_id=new_job.id,
            llm_provider=llm_provider,
            note_types=note_types,
            topic_ids=topic_ids,
            force_regenerate=force_regen,
        )
    else:
        background_tasks.add_task(
            run_extraction_job_in_session,
            session_factory=session_factory,
            storage_root=settings.storage_root,
            document_id=new_job.document_id,
            job_id=new_job.id,
            mode=new_job.job_type,
            force_reextract=True,
        )
    return new_job
