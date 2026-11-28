from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class QuestionOptionOut(BaseModel):
    """Public question option (never carries an `is_correct` flag)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    option_key: str
    option_text: str
    display_order: int


class QuestionOptionInput(BaseModel):
    """Input option payload for question import or editing."""

    key: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1)


class QuestionOut(BaseModel):
    """Question Bank summary/list schema (for non-active-test contexts only)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID | None = None
    topic_id: UUID | None = None
    topic_name: str | None = None
    concept_id: UUID | None = None
    exam_config_id: UUID | None = None
    subject_code: str
    question_text: str
    question_type: str
    difficulty: str
    origin: str
    source_page_number: int | None = None
    supporting_excerpt: str | None = None
    diagram_asset_id: UUID | None = None
    passage_group_id: UUID | None = None
    passage_text: str | None = None
    pyq_metadata_json: dict[str, Any] | None = None
    options: list[QuestionOptionOut] = Field(default_factory=list)
    correct_option_key: str | None = None
    explanation: str = ""
    answer_key_provenance: str
    validation_status: str
    validation_warnings: list[str] = Field(default_factory=list)
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    created_at: datetime
    updated_at: datetime


class QuestionDetailOut(QuestionOut):
    """Full question detail schema for Question Bank inspection outside active tests."""

    correct_answer_data: dict[str, Any] = Field(default_factory=dict)


class QuestionListResponse(BaseModel):
    """Paginated Question Bank response."""

    items: list[QuestionOut]
    total: int
    limit: int
    offset: int


class QuestionIngestionSummary(BaseModel):
    """Summary returned after ingesting extracted or imported question candidates."""

    document_id: UUID
    total_received: int
    inserted_count: int
    skipped_duplicate_count: int
    verified_count: int
    needs_review_count: int
    question_ids: list[UUID] = Field(default_factory=list)


class QuestionGenerateRequest(BaseModel):
    """Request to generate new MCQs from stored concepts, facts, and topics."""

    document_id: UUID | None = None
    topic_id: UUID | None = None
    concept_id: UUID | None = None
    subject_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("subject_code", "subject"),
    )
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    count: int = Field(default=5, ge=1, le=20)


class QuestionGenerateResponse(BaseModel):
    """Response summarizing generated and validated MCQs."""

    created: list[QuestionDetailOut]
    verified_count: int
    needs_review_count: int
    duplicates_skipped: int


class PYQImportItem(BaseModel):
    """Single structured PYQ item for JSON or CSV import."""

    question_text: str = Field(min_length=1)
    options: list[QuestionOptionInput] = Field(default_factory=list)
    correct_option_key: str | None = None
    explanation: str = ""
    subject_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("subject_code", "subject"),
    )
    topic_name: str | None = None
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    source_page_number: int | None = None
    supporting_excerpt: str | None = None
    pyq_metadata: dict[str, Any] | None = None
    passage_text: str | None = None
    passage_group_id: UUID | None = None


class QuestionImportRequest(BaseModel):
    """Batch PYQ import payload supporting structured JSON items or CSV text."""

    document_id: UUID | None = None
    exam_config_id: UUID | None = None
    default_subject_code: str = "unknown"
    answer_key_provenance: Literal["source_answer_key", "user_supplied"] = "user_supplied"
    items: list[PYQImportItem] = Field(default_factory=list)
    csv_content: str | None = None


class QuestionImportResponse(BaseModel):
    """Response returned after importing and validating PYQ questions."""

    imported_count: int
    verified_count: int
    needs_review_count: int
    duplicates_skipped: int
    items: list[QuestionDetailOut]


class QuestionUpdateRequest(BaseModel):
    """Manual review/correction payload for a Question Bank item."""

    question_text: str | None = None
    options: list[QuestionOptionInput] | None = None
    correct_option_key: str | None = None
    explanation: str | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    topic_id: UUID | None = None
    validation_status: Literal["verified", "needs_review", "rejected"] | None = None


class DeleteQuestionResponse(BaseModel):
    """Confirmation payload for deleted question."""

    deleted_id: UUID
