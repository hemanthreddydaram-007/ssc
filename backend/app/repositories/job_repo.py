from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db.base import utcnow
from app.models.document import Document, DocumentAsset, DocumentPage, ProcessingJob
from app.schemas.job import (
    AssetSummaryOut,
    CoverageAuditOut,
    DocumentPageOut,
    DocumentPagesResponse,
    JobListResponse,
    ProcessingJobOut,
)
from app.services.assessment.timer_service import ensure_utc

INTERRUPTED_ERROR_CODE = "JOB_INTERRUPTED"
INTERRUPTED_ERROR_MESSAGE = (
    "Processing was interrupted because the server restarted or went to sleep. "
    "Click Retry to run again."
)
DEFAULT_STALE_JOB_TIMEOUT = timedelta(minutes=10)
DEFAULT_GENERATE_NOTE_TYPES: list[str] = [
    "detailed",
    "quick_revision",
    "formula_sheet",
    "strategy_sheet",
]

_HEARTBEAT_LOCK = threading.Lock()
_ACTIVE_JOB_HEARTBEATS: dict[UUID, float] = {}


def register_active_job(job_id: UUID) -> None:
    """Record that a background job is actively executing in the current process."""
    with _HEARTBEAT_LOCK:
        _ACTIVE_JOB_HEARTBEATS[job_id] = time.monotonic()


def touch_job_heartbeat(job_id: UUID) -> None:
    """Refresh the monotonic heartbeat timestamp for a running background job."""
    with _HEARTBEAT_LOCK:
        _ACTIVE_JOB_HEARTBEATS[job_id] = time.monotonic()


def unregister_active_job(job_id: UUID) -> None:
    """Remove a finished/failed background job from the active process registry."""
    with _HEARTBEAT_LOCK:
        _ACTIVE_JOB_HEARTBEATS.pop(job_id, None)


def _is_job_heartbeat_fresh(job_id: UUID, *, stale_seconds: float) -> bool:
    with _HEARTBEAT_LOCK:
        ts = _ACTIVE_JOB_HEARTBEATS.get(job_id)
    if ts is None:
        return False
    return (time.monotonic() - ts) <= stale_seconds


def mark_job_interrupted(job: ProcessingJob, *, now: datetime | None = None) -> None:
    """Transition an orphaned queued/running job and its active stage to retryable failure."""
    ts = now or utcnow()
    job.status = "failed"
    job.error_code = INTERRUPTED_ERROR_CODE
    job.error_message = INTERRUPTED_ERROR_MESSAGE
    job.finished_at = ts

    raw_stages = list(job.stage_details_json or [])
    stages: list[dict[str, Any]] = [dict(s) for s in raw_stages if isinstance(s, dict)]
    marked = False
    for stage in stages:
        if stage.get("status") == "running":
            stage["status"] = "failed"
            stage["error_code"] = INTERRUPTED_ERROR_CODE
            stage["error_message"] = INTERRUPTED_ERROR_MESSAGE
            stage["retryable"] = True
            marked = True
    if not marked and job.current_stage:
        for stage in stages:
            if stage.get("name") == job.current_stage:
                stage["status"] = "failed"
                stage["error_code"] = INTERRUPTED_ERROR_CODE
                stage["error_message"] = INTERRUPTED_ERROR_MESSAGE
                stage["retryable"] = True
                marked = True
                break
    if not marked:
        for stage in stages:
            if stage.get("status") == "pending":
                stage["status"] = "failed"
                stage["error_code"] = INTERRUPTED_ERROR_CODE
                stage["error_message"] = INTERRUPTED_ERROR_MESSAGE
                stage["retryable"] = True
                break
    job.stage_details_json = stages
    flag_modified(job, "stage_details_json")


def _is_job_stale(
    job: ProcessingJob,
    *,
    now: datetime,
    stale_after: timedelta | None,
    ignore_heartbeats: bool,
) -> bool:
    if job.status not in ("queued", "running"):
        return False
    if not ignore_heartbeats:
        timeout_secs = stale_after.total_seconds() if stale_after is not None else 0.0
        if _is_job_heartbeat_fresh(job.id, stale_seconds=timeout_secs):
            return False
    if stale_after is None:
        return True
    ref_time = ensure_utc(job.started_at or job.created_at)
    if ref_time is None:
        return True
    return (now - ref_time) > stale_after


def recover_stale_jobs(
    db: Session,
    *,
    stale_after: timedelta | None = DEFAULT_STALE_JOB_TIMEOUT,
    ignore_heartbeats: bool = False,
) -> int:
    """Recover orphaned queued/running processing jobs as retryable JOB_INTERRUPTED failures."""
    candidates = list(
        db.execute(
            select(ProcessingJob).where(ProcessingJob.status.in_(("queued", "running")))
        )
        .scalars()
        .all()
    )
    if not candidates:
        return 0
    now = utcnow()
    recovered = 0
    for job in candidates:
        if _is_job_stale(
            job,
            now=now,
            stale_after=stale_after,
            ignore_heartbeats=ignore_heartbeats,
        ):
            mark_job_interrupted(job, now=now)
            db.add(job)
            recovered += 1
    if recovered > 0:
        db.commit()
    return recovered


def build_note_job_stages(
    *,
    note_types: list[str] | None = None,
    topic_ids: list[UUID] | None = None,
    force_regenerate: bool = False,
) -> list[dict[str, Any]]:
    """Build note-generation stages and embed retry params (ignored by JobStageOut)."""
    from app.services.notes.generator import _make_note_stages  # noqa: PLC0415

    stages = _make_note_stages()
    params = {
        "note_types": list(note_types) if note_types else list(DEFAULT_GENERATE_NOTE_TYPES),
        "topic_ids": [str(tid) for tid in topic_ids] if topic_ids is not None else None,
        "force_regenerate": bool(force_regenerate),
    }
    for stage in stages:
        if stage.get("name") == "generate_notes":
            stage["_params"] = params
            break
    return stages


def extract_note_job_params(
    stage_details_json: list[Any] | None,
) -> tuple[list[str], list[UUID] | None, bool]:
    """Recover saved note-generation parameters from stage metadata, or safe defaults."""
    for stage in stage_details_json or []:
        if not isinstance(stage, dict):
            continue
        params = stage.get("_params")
        if not isinstance(params, dict):
            continue
        raw_types = params.get("note_types")
        note_types = (
            [str(nt) for nt in raw_types if nt]
            if isinstance(raw_types, list) and raw_types
            else list(DEFAULT_GENERATE_NOTE_TYPES)
        )
        raw_topics = params.get("topic_ids")
        topic_ids: list[UUID] | None = None
        if isinstance(raw_topics, list):
            parsed_topics: list[UUID] = []
            for raw_tid in raw_topics:
                try:
                    parsed_topics.append(UUID(str(raw_tid)))
                except ValueError:
                    continue
            topic_ids = parsed_topics
        force_regenerate = bool(params.get("force_regenerate", False))
        return note_types, topic_ids, force_regenerate
    return list(DEFAULT_GENERATE_NOTE_TYPES), None, False


class JobNotFoundError(Exception):
    """Raised when a processing job cannot be found."""


class JobAccessDeniedError(Exception):
    """Raised when a processing job belongs to another user."""


class AssetNotFoundError(Exception):
    """Raised when a document asset cannot be found."""


def _job_to_out(job: ProcessingJob, *, document_title: str | None = None) -> ProcessingJobOut:
    """Convert a ProcessingJob ORM object to its public schema."""
    progress: int | None = None
    if job.total_items and job.total_items > 0:
        progress = int(min(100, round(job.processed_items * 100 / job.total_items)))
    return ProcessingJobOut(
        id=job.id,
        document_id=job.document_id,
        document_title=document_title,
        job_type=job.job_type,
        status=job.status,
        current_stage=job.current_stage,
        stages=job.stage_details_json or [],
        processed_items=job.processed_items,
        total_items=job.total_items,
        progress_percent=progress,
        error_code=job.error_code,
        error_message=job.error_message,
        retry_count=job.retry_count,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


class JobRepository:
    """Data-access layer for processing jobs, extracted pages, and assets."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_job(self, job_id: UUID) -> ProcessingJob | None:
        job = self.db.get(ProcessingJob, job_id)
        if job is not None and _is_job_stale(
            job,
            now=utcnow(),
            stale_after=DEFAULT_STALE_JOB_TIMEOUT,
            ignore_heartbeats=False,
        ):
            mark_job_interrupted(job)
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
        return job

    def list_jobs(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ProcessingJob], int]:
        rows, total = self.list_jobs_with_titles(
            user_id=user_id,
            document_id=document_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [job for job, _title in rows], total

    def list_jobs_with_titles(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[ProcessingJob, str]], int]:
        recover_stale_jobs(self.db, stale_after=DEFAULT_STALE_JOB_TIMEOUT, ignore_heartbeats=False)

        conditions = [
            Document.user_id == user_id,
            Document.deleted_at.is_(None),
        ]
        if document_id:
            conditions.append(ProcessingJob.document_id == document_id)
        if status:
            conditions.append(ProcessingJob.status == status)

        count_q = (
            select(func.count())
            .select_from(ProcessingJob)
            .join(Document, ProcessingJob.document_id == Document.id)
            .where(*conditions)
        )
        items_q = (
            select(ProcessingJob, Document.title)
            .join(Document, ProcessingJob.document_id == Document.id)
            .where(*conditions)
            .order_by(ProcessingJob.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        total = int(self.db.execute(count_q).scalar_one())
        rows = [(row[0], row[1]) for row in self.db.execute(items_q).all()]
        return rows, total

    def create_job(self, job: ProcessingJob) -> ProcessingJob:
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def save_job(self, job: ProcessingJob) -> ProcessingJob:
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_pages(
        self, document_id: UUID, *, needs_ocr_only: bool = False
    ) -> list[DocumentPage]:
        q = select(DocumentPage).where(DocumentPage.document_id == document_id)
        if needs_ocr_only:
            q = q.where(DocumentPage.needs_ocr == True)  # noqa: E712
        return list(self.db.execute(q.order_by(DocumentPage.page_number)).scalars().all())

    def get_assets_for_pages(self, document_id: UUID) -> dict[int, list[DocumentAsset]]:
        """Return a mapping of page_number -> list[DocumentAsset]."""
        assets = list(
            self.db.execute(
                select(DocumentAsset)
                .where(DocumentAsset.document_id == document_id)
                .order_by(DocumentAsset.created_at)
            )
            .scalars()
            .all()
        )
        mapping: dict[int, list[DocumentAsset]] = {}
        for asset in assets:
            mapping.setdefault(asset.page_number, []).append(asset)
        return mapping

    def get_asset_by_id(self, document_id: UUID, asset_id: UUID) -> DocumentAsset | None:
        return self.db.execute(
            select(DocumentAsset).where(
                DocumentAsset.id == asset_id,
                DocumentAsset.document_id == document_id,
            )
        ).scalar_one_or_none()


class JobService:
    """Service layer for processing jobs, page review, asset streaming, and coverage audit."""

    def __init__(self, db: Session) -> None:
        self.repo = JobRepository(db)
        self.db = db

    def _resolve_document_title(
        self, document_id: UUID, document_title: str | None = None
    ) -> str | None:
        if document_title is not None:
            return document_title
        doc = self.db.get(Document, document_id)
        return doc.title if doc is not None and doc.deleted_at is None else None

    def create_extraction_job(
        self,
        *,
        document_id: UUID,
        user_id: UUID,
        job_type: str = "extract_only",
        retry_count: int = 0,
        document_title: str | None = None,
    ) -> ProcessingJobOut:
        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=document_id,
            triggered_by_user_id=user_id,
            job_type=job_type,
            status="queued",
            current_stage="queued",
            stage_details_json=[
                {
                    "name": "page_extraction",
                    "status": "pending",
                    "processed_items": None,
                    "total_items": None,
                    "error_code": None,
                    "error_message": None,
                    "retryable": True,
                },
                {
                    "name": "ocr_fallback",
                    "status": "pending",
                    "processed_items": None,
                    "total_items": None,
                    "error_code": None,
                    "error_message": None,
                    "retryable": True,
                },
                {
                    "name": "semantic_chunking",
                    "status": "pending",
                    "processed_items": None,
                    "total_items": None,
                    "error_code": None,
                    "error_message": None,
                    "retryable": True,
                },
                {
                    "name": "coverage_audit",
                    "status": "pending",
                    "processed_items": None,
                    "total_items": None,
                    "error_code": None,
                    "error_message": None,
                    "retryable": True,
                },
            ],
            processed_items=0,
            total_items=0,
            progress_percent=None,
            retry_count=retry_count,
        )
        created = self.repo.create_job(job)
        resolved_title = self._resolve_document_title(document_id, document_title)
        return _job_to_out(created, document_title=resolved_title)

    def get_owned_job(self, *, job_id: UUID, user_id: UUID) -> ProcessingJobOut:
        job = self.repo.get_job(job_id)
        if job is None:
            raise JobNotFoundError("Processing job not found")
        doc = self.db.get(Document, job.document_id)
        if doc is None or doc.deleted_at is not None:
            raise JobNotFoundError("Associated document not found")
        if doc.user_id != user_id:
            raise JobAccessDeniedError("You do not have access to this processing job")
        return _job_to_out(job, document_title=doc.title)

    def prepare_retry_job(self, *, job_id: UUID, user_id: UUID) -> ProcessingJobOut:
        prior = self.repo.get_job(job_id)
        if prior is None:
            raise JobNotFoundError("Processing job not found")
        doc = self.db.get(Document, prior.document_id)
        if doc is None or doc.deleted_at is not None:
            raise JobNotFoundError("Associated document not found")
        if doc.user_id != user_id:
            raise JobAccessDeniedError("You do not have access to this processing job")

        if prior.job_type == "extract_knowledge":
            from app.services.knowledge.extractor import _make_knowledge_stages  # noqa: PLC0415

            job = ProcessingJob(
                id=uuid.uuid4(),
                document_id=prior.document_id,
                triggered_by_user_id=user_id,
                job_type="extract_knowledge",
                status="queued",
                current_stage="queued",
                stage_details_json=_make_knowledge_stages(),
                processed_items=0,
                total_items=prior.total_items or 0,
                progress_percent=0,
                retry_count=prior.retry_count + 1,
            )
            created = self.repo.create_job(job)
            return _job_to_out(created, document_title=doc.title)

        if prior.job_type == "generate_notes":
            note_types, topic_ids, force_regen = extract_note_job_params(prior.stage_details_json)
            job = ProcessingJob(
                id=uuid.uuid4(),
                document_id=prior.document_id,
                triggered_by_user_id=user_id,
                job_type="generate_notes",
                status="queued",
                current_stage="queued",
                stage_details_json=build_note_job_stages(
                    note_types=note_types,
                    topic_ids=topic_ids,
                    force_regenerate=force_regen,
                ),
                processed_items=0,
                total_items=prior.total_items or 0,
                progress_percent=0,
                retry_count=prior.retry_count + 1,
            )
            created = self.repo.create_job(job)
            return _job_to_out(created, document_title=doc.title)

        return self.create_extraction_job(
            document_id=prior.document_id,
            user_id=user_id,
            job_type=prior.job_type,
            retry_count=prior.retry_count + 1,
            document_title=doc.title,
        )

    def get_retry_note_params(
        self, job_id: UUID
    ) -> tuple[list[str], list[UUID] | None, bool]:
        """Fetch persisted note generation parameters for a queued retry job."""
        job = self.db.get(ProcessingJob, job_id)
        if job is None:
            return list(DEFAULT_GENERATE_NOTE_TYPES), None, False
        return extract_note_job_params(job.stage_details_json)

    def list_jobs(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> JobListResponse:
        rows, total = self.repo.list_jobs_with_titles(
            user_id=user_id,
            document_id=document_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return JobListResponse(
            items=[_job_to_out(j, document_title=doc_title) for j, doc_title in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_pages(
        self, document_id: UUID, *, needs_ocr_only: bool = False
    ) -> DocumentPagesResponse:
        pages = self.repo.get_pages(document_id, needs_ocr_only=needs_ocr_only)
        assets_by_page = self.repo.get_assets_for_pages(document_id)

        page_outs = []
        for p in pages:
            asset_outs = [
                AssetSummaryOut(
                    id=a.id,
                    page_number=a.page_number,
                    asset_type=a.asset_type,
                    mime_type=a.mime_type,
                    width=a.width,
                    height=a.height,
                )
                for a in assets_by_page.get(p.page_number, [])
            ]
            page_outs.append(
                DocumentPageOut(
                    id=p.id,
                    page_number=p.page_number,
                    extracted_text=p.extracted_text,
                    extraction_method=p.extraction_method,
                    confidence=p.confidence,
                    processing_status=p.processing_status,
                    needs_ocr=p.needs_ocr,
                    ocr_provider=p.ocr_provider,
                    raw_char_count=p.raw_char_count,
                    image_count=p.image_count,
                    table_count=p.table_count,
                    tables_json=p.tables_json,
                    warning=p.warning,
                    assets=asset_outs,
                )
            )

        doc = self.db.get(Document, document_id)
        page_count = doc.page_count if doc else len(page_outs)

        return DocumentPagesResponse(
            document_id=document_id,
            page_count=page_count,
            items=page_outs,
        )

    def get_asset(self, *, document_id: UUID, asset_id: UUID) -> DocumentAsset:
        asset = self.repo.get_asset_by_id(document_id, asset_id)
        if asset is None:
            raise AssetNotFoundError("Document asset not found")
        return asset

    def get_coverage_audit(self, document_id: UUID) -> CoverageAuditOut:
        from app.services.extraction.coverage_audit import build_coverage_audit  # noqa: PLC0415

        return build_coverage_audit(self.db, document_id)
