from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TopicSummaryOut(BaseModel):
    """Topic summary with optional document- or user-scoped counts and source pages."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_code: str
    exam_config_id: UUID | None = None
    parent_topic_id: UUID | None = None
    name: str
    slug: str
    description: str | None = None
    is_canonical: bool = False
    sort_order: int = 0
    concept_count: int = 0
    fact_count: int = 0
    question_count: int = 0
    source_pages: list[int] = Field(default_factory=list)


class TopicListResponse(BaseModel):
    """List response for document-scoped or global topics."""

    items: list[TopicSummaryOut]
    total: int


class SubjectCapabilityOut(BaseModel):
    """Public capability metadata for a configured subject adapter."""

    subject_code: str
    display_name: str
    supported_strategies: list[str] = Field(default_factory=list)


class SubjectListResponse(BaseModel):
    """List response for `/api/v1/subjects`."""

    items: list[SubjectCapabilityOut]
