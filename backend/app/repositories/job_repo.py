from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentAsset, DocumentPage, ProcessingJob
from app.schemas.job import (
    AssetSummaryOut,
    CoverageAuditOut,
    DocumentPageOut,
    DocumentPagesResponse,
    JobListResponse,
    ProcessingJobOut,
)
from app.services.extraction.coverage_audit import build_coverage_audit


class JobNotFoundError(Exception):
    """Raised when a processing job cannot be found."""


class JobAccessDeniedError(Exception):
    """Raised when a processing job belongs to another user."""


class AssetNotFoundError(Exception):
    """Raised when a document asset cannot be found."""


def _job_to_out(job: ProcessingJob) -> ProcessingJobOut:
    """Convert a ProcessingJob ORM object to its public schema."""
    progress: int | None = None
    if job.total_items and job.total_items > 0:
        progress = int(min(100, round(job.processed_items * 100 / job.total_items)))
    return ProcessingJobOut(
        id=job.id,
        document_id=job.document_id,
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
        return self.db.get(ProcessingJob, job_id)

    def list_jobs(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ProcessingJob], int]:
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
            select(ProcessingJob)
            .join(Document, ProcessingJob.document_id == Document.id)
            .where(*conditions)
            .order_by(ProcessingJob.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        total = int(self.db.execute(count_q).scalar_one())
        items = list(self.db.execute(items_q).scalars().all())
        return items, total

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

    def create_extraction_job(
        self,
        *,
        document_id: UUID,
        user_id: UUID,
        job_type: str = "extract_only",
        retry_count: int = 0,
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
        return _job_to_out(created)

    def get_owned_job(self, *, job_id: UUID, user_id: UUID) -> ProcessingJobOut:
        job = self.repo.get_job(job_id)
        if job is None:
            raise JobNotFoundError("Processing job not found")
        doc = self.db.get(Document, job.document_id)
        if doc is None or doc.deleted_at is not None:
            raise JobNotFoundError("Associated document not found")
        if doc.user_id != user_id:
            raise JobAccessDeniedError("You do not have access to this processing job")
        return _job_to_out(job)

    def prepare_retry_job(self, *, job_id: UUID, user_id: UUID) -> ProcessingJobOut:
        prior = self.repo.get_job(job_id)
        if prior is None:
            raise JobNotFoundError("Processing job not found")
        doc = self.db.get(Document, prior.document_id)
        if doc is None or doc.deleted_at is not None:
            raise JobNotFoundError("Associated document not found")
        if doc.user_id != user_id:
            raise JobAccessDeniedError("You do not have access to this processing job")
        return self.create_extraction_job(
            document_id=prior.document_id,
            user_id=user_id,
            job_type=prior.job_type,
            retry_count=prior.retry_count + 1,
        )

    def list_jobs(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> JobListResponse:
        items, total = self.repo.list_jobs(
            user_id=user_id,
            document_id=document_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return JobListResponse(
            items=[_job_to_out(j) for j in items],
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
        return build_coverage_audit(self.db, document_id)
