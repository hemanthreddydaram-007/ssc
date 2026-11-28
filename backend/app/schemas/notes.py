from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

NoteType = Literal["detailed", "quick_revision", "formula_sheet", "strategy_sheet"]
NoteBlockType = Literal[
    "concept",
    "definition",
    "step",
    "worked_example",
    "formula",
    "rule",
    "misconception",
    "comparison",
    "mnemonic",
    "recap",
    "strategy",
    "warning",
]
NoteProvenance = Literal[
    "extracted",
    "paraphrased",
    "ai_explanation",
    "externally_verified",
    "unverified",
]
NoteReviewStatus = Literal["verified", "needs_review", "conflict"]


class NoteSourceRef(BaseModel):
    """Source citation linking a note block back to its supporting document page."""

    document_id: UUID | None = None
    page_number: int | None = None
    supporting_excerpt: str = ""


class NoteBlock(BaseModel):
    """Single structured block inside a note section."""

    block_type: NoteBlockType = "concept"
    title: str | None = None
    body: str
    formula_latex: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: NoteProvenance = "ai_explanation"
    source_refs: list[NoteSourceRef] = Field(default_factory=list)
    review_status: NoteReviewStatus = "verified"


class NoteSection(BaseModel):
    """Logical section inside `NoteContentJson`."""

    key: str
    title: str
    blocks: list[NoteBlock] = Field(default_factory=list)


class NoteContentJson(BaseModel):
    """Canonical `content_json` payload stored on `Note` records."""

    summary: str = ""
    sections: list[NoteSection] = Field(default_factory=list)
    one_minute_recap: str | None = None
    insufficient_evidence_message: str | None = None


class GenerateNotesRequest(BaseModel):
    """Request body for `POST /api/v1/documents/{id}/generate-notes`."""

    note_types: list[NoteType] = Field(
        default_factory=lambda: ["detailed", "quick_revision", "formula_sheet", "strategy_sheet"],
        min_length=1,
    )
    topic_ids: list[UUID] | None = None
    max_topics: int | None = Field(default=None, ge=1, le=200)
    force_regenerate: bool = False


class RegenerateNoteRequest(BaseModel):
    """Request body for `POST /api/v1/notes/{id}/regenerate`."""

    section_keys: list[str] | None = None
    custom_instruction: str | None = Field(default=None, max_length=1000)


class NoteUpdateRequest(BaseModel):
    """Request body for `PATCH /api/v1/notes/{id}`."""

    understood: bool | None = None
    status: Literal["ready", "needs_review", "insufficient_evidence"] | None = None


class NoteSummaryOut(BaseModel):
    """Compact summary item returned by note list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    topic_id: UUID | None = None
    topic_name: str | None = None
    subject_code: str | None = None
    note_type: str
    title: str
    generation_version: int
    status: str
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    understood_at: datetime | None = None
    created_at: datetime


class NoteListResponse(BaseModel):
    """Paginated list of notes."""

    items: list[NoteSummaryOut]
    total: int


class NoteDetailOut(BaseModel):
    """Full note detail including structured `content_json` and provenance links."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    topic_id: UUID | None = None
    topic_name: str | None = None
    subject_code: str | None = None
    note_type: str
    title: str
    content_json: dict[str, Any] = Field(default_factory=dict)
    source_concept_ids: list[UUID] = Field(default_factory=list)
    source_fact_ids: list[UUID] = Field(default_factory=list)
    generation_version: int
    status: str
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    understood_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime


class PYQSubjectStat(BaseModel):
    """Sample-scoped subject frequency with explicit percentage."""

    subject_code: str
    count: int
    percentage: float


class PYQTopicStat(BaseModel):
    """Sample-scoped topic frequency."""

    topic_id: UUID | None = None
    topic_name: str
    count: int
    percentage: float


class PYQPatternsOut(BaseModel):
    """Sample-scoped PYQ pattern analysis with explicit denominator."""

    document_id: UUID
    total_questions_analyzed: int
    sample_note: str
    subjects: list[PYQSubjectStat] = Field(default_factory=list)
    topics: list[PYQTopicStat] = Field(default_factory=list)
    difficulty_distribution: dict[str, int] = Field(default_factory=dict)
    years_shifts: list[dict[str, Any]] = Field(default_factory=list)
    repeated_templates: list[dict[str, Any]] = Field(default_factory=list)
