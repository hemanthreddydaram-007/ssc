from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobStageOut(BaseModel):
    """Public representation of a single processing pipeline stage."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    status: str  # queued | running | completed | failed | skipped
    processed_items: int | None = None
    total_items: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False


class ProcessingJobOut(BaseModel):
    """Public representation of a document processing job."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_title: str | None = None
    job_type: str
    status: str  # queued | running | completed | failed | cancelled
    current_stage: str
    stages: list[JobStageOut] = Field(default_factory=list)
    processed_items: int
    total_items: int
    # Strictly derived from real counts; None when total_items is 0 or unknown.
    progress_percent: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ProcessDocumentRequest(BaseModel):
    """Request body for triggering document extraction."""

    mode: Literal["extract_only", "full", "ocr_retry"] = Field(
        default="extract_only",
        description="One of: extract_only, full, ocr_retry",
    )
    page_numbers: list[int] | None = None
    force_reextract: bool = False


class JobListResponse(BaseModel):
    """Paginated list of processing jobs."""

    items: list[ProcessingJobOut]
    total: int
    limit: int
    offset: int


class AssetSummaryOut(BaseModel):
    """Lightweight asset reference embedded in page responses (no storage_key)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_number: int
    asset_type: str
    mime_type: str
    width: int
    height: int


class DocumentPageOut(BaseModel):
    """Public per-page extraction result."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    page_number: int
    extracted_text: str
    extraction_method: str
    confidence: float
    processing_status: str
    needs_ocr: bool
    ocr_provider: str | None = None
    raw_char_count: int
    image_count: int
    table_count: int
    tables_json: list[object] | None = None
    warning: str | None = None
    assets: list[AssetSummaryOut] = Field(default_factory=list)


class DocumentPagesResponse(BaseModel):
    """Full page extraction review for a document."""

    document_id: UUID
    page_count: int
    items: list[DocumentPageOut]


class LowConfidencePageOut(BaseModel):
    """Page with low extraction confidence or OCR requirement."""

    page_number: int
    confidence: float
    extraction_method: str
    warning: str | None = None


class CoverageAuditOut(BaseModel):
    """Coverage audit report for a document."""

    document_id: UUID
    total_pages: int
    pages_extracted_text: int
    pages_extracted_ocr: int
    pages_requiring_ocr: int
    pages_not_processed: int
    low_confidence_pages: list[LowConfidencePageOut] = Field(default_factory=list)
    tables_extracted: int
    images_extracted: int
    chunks_created: int
    facts_extracted: int
    concepts_identified: int
    questions_extracted: int
    records_rejected_or_uncertain: int
    low_confidence_topics: list[str] = Field(default_factory=list)
