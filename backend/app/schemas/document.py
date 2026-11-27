from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal["pdf", "image", "plain_text"]


class DocumentOut(BaseModel):
    """Public representation of an uploaded or pasted document.

    Deliberately excludes internal `storage_key` and soft-delete metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    original_filename: str
    source_type: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    exam_config_id: UUID | None = None
    subject_code: str | None = None
    detected_subject_code: str | None = None
    classification_confidence: float | None = None
    chapter_or_topic_hint: str | None = None
    material_type: str
    language: str
    source_label: str | None = None
    page_count: int
    status: str
    extraction_version: str | None = None
    coverage_summary_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Paginated list of user documents."""

    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


class TextIngestionRequest(BaseModel):
    """Payload for ingesting plain text pasted by the student."""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    exam_config_id: UUID | None = None
    subject_code: str | None = Field(default=None, max_length=64)
    chapter_or_topic_hint: str | None = Field(default=None, max_length=255)
    material_type: str = Field(default="other", min_length=1, max_length=64)
    language: str = Field(default="en", min_length=1, max_length=32)
    source_label: str | None = Field(default=None, max_length=255)
    allow_duplicate: bool = False

    @field_validator("title", "content")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank")
        return stripped

    @field_validator(
        "subject_code", "chapter_or_topic_hint", "material_type", "language", "source_label"
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class DocumentUpdateRequest(BaseModel):
    """Fields a user can update on an existing document."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    exam_config_id: UUID | None = None
    subject_code: str | None = Field(default=None, max_length=64)
    chapter_or_topic_hint: str | None = Field(default=None, max_length=255)
    material_type: str | None = Field(default=None, min_length=1, max_length=64)
    language: str | None = Field(default=None, min_length=1, max_length=32)
    source_label: str | None = Field(default=None, max_length=255)

    @field_validator("title", "material_type", "language")
    @classmethod
    def _strip_non_blank_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank")
        return stripped

    @field_validator("subject_code", "chapter_or_topic_hint", "source_label")
    @classmethod
    def _normalize_nullable(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class DeleteDocumentResponse(BaseModel):
    """Result returned after deleting a document."""

    deleted_id: UUID
    storage_removed: bool


class DuplicateDocumentResponse(BaseModel):
    """Error payload returned on duplicate upload when `allow_duplicate` is false."""

    detail: str
    code: str = "DUPLICATE_DOCUMENT"
    existing_document_id: UUID
