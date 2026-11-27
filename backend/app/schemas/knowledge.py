from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.topics import TopicSummaryOut


class CandidateOption(BaseModel):
    """Choice option on an extracted question candidate."""

    key: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1)


class ExtractedQuestionCandidate(BaseModel):
    """Shared handoff DTO emitted by knowledge extraction for `@assessment-engineer`."""

    question_text: str
    question_type: str = "single_choice"
    subject_code: str
    topic_name: str | None = None
    difficulty: str = "medium"
    options: list[CandidateOption] = Field(default_factory=list)
    correct_option_key: str | None = None
    explanation: str = ""
    source_page_number: int | None = None
    supporting_excerpt: str | None = None
    answer_key_provenance: str = "source_answer_key"
    pyq_metadata: dict[str, Any] | None = None
    passage_text: str | None = None
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None


class ExtractKnowledgeRequest(BaseModel):
    """Optional request body for `POST /api/v1/documents/{id}/extract-knowledge`."""

    force_reprocess: bool = False


class ClassificationOverrideRequest(BaseModel):
    """User manual override for document classification fields."""

    subject_code: str | None = Field(default=None, max_length=64)
    material_type: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=32)

    @field_validator("subject_code", "material_type", "language")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ConceptOut(BaseModel):
    """Public representation of an extracted concept record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    topic_id: UUID | None = None
    title: str
    explanation: str
    difficulty: str | None = None
    provenance: str
    confidence: float
    review_status: str
    source_refs_json: list[Any] = Field(default_factory=list)
    prerequisites_json: list[Any] = Field(default_factory=list)
    related_concept_ids_json: list[Any] = Field(default_factory=list)
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    created_at: datetime


class FactOut(BaseModel):
    """Public representation of an extracted fact, formula, or rule record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    topic_id: UUID | None = None
    chunk_id: UUID | None = None
    fact_type: str
    content: str
    provenance: str
    confidence: float
    source_page_number: int | None = None
    supporting_excerpt: str | None = None
    source_refs_json: list[Any] = Field(default_factory=list)
    conflict_group_id: UUID | None = None
    is_time_sensitive: bool = False
    source_date_label: str | None = None
    review_status: str
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    created_at: datetime


class FactUpdateRequest(BaseModel):
    """Manual review/correction payload for `PATCH /api/v1/facts/{id}`."""

    content: str | None = Field(default=None, min_length=1)
    fact_type: str | None = Field(default=None, min_length=1, max_length=64)
    review_status: Literal["verified", "needs_review", "conflict", "rejected"] | None = None

    @field_validator("content", "fact_type")
    @classmethod
    def _strip_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank")
        return stripped


class DocumentKnowledgeOut(BaseModel):
    """Full structured knowledge view for a document."""

    document_id: UUID
    subject_code: str | None = None
    detected_subject_code: str | None = None
    classification_confidence: float | None = None
    topics: list[TopicSummaryOut] = Field(default_factory=list)
    concepts: list[ConceptOut] = Field(default_factory=list)
    facts: list[FactOut] = Field(default_factory=list)
    rejected_or_uncertain_count: int = 0
