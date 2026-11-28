from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DifficultyMix(BaseModel):
    """Target counts or relative weights per difficulty tier."""

    easy: int = Field(default=0, ge=0)
    medium: int = Field(default=0, ge=0)
    hard: int = Field(default=0, ge=0)


class TestPreviewRequest(BaseModel):
    """Query criteria to preview matching Question Bank availability before building a test."""

    document_ids: list[UUID] | None = None
    subject_codes: list[str] | None = None
    topic_ids: list[UUID] | None = None
    question_ids: list[UUID] | None = None
    origin_mode: Literal["extracted", "generated", "mixed"] = "mixed"
    difficulty_mix: DifficultyMix | None = None
    question_count: int = Field(default=10, ge=1, le=200)
    include_needs_review: bool = False


class TestPreviewResponse(BaseModel):
    """Matching Question Bank breakdown returned by `/tests/preview`."""

    available_count: int
    by_difficulty: dict[str, int]
    by_subject: dict[str, int]
    can_satisfy: bool
    shortfall_reason: str | None = None


class TestCreateRequest(BaseModel):
    """Configuration payload to create a test with immutable question snapshots."""

    title: str = Field(min_length=1, max_length=255)
    exam_config_id: UUID | None = None
    document_ids: list[UUID] | None = None
    subject_codes: list[str] | None = None
    topic_ids: list[UUID] | None = None
    question_ids: list[UUID] | None = None
    question_count: int = Field(default=10, ge=1, le=200)
    origin_mode: Literal["extracted", "generated", "mixed"] = "mixed"
    difficulty_mix: DifficultyMix | None = None
    timer_mode: Literal["speed_challenge", "exam_simulation", "learning_mode"] = "speed_challenge"
    per_question_seconds: int = Field(default=35, ge=5, le=600)
    total_duration_seconds: int | None = Field(default=None, ge=30, le=18000)
    auto_advance_on_timeout: bool = True
    points_per_question: Decimal = Field(default=Decimal("2.00"), gt=Decimal("0"))
    negative_marking_enabled: bool = False
    negative_points: Decimal = Field(default=Decimal("0.50"), ge=Decimal("0"))
    shuffle_questions: bool = False
    shuffle_options: bool = False
    show_explanation_after: Literal["after_question", "after_submission"] = "after_submission"
    hints_enabled: bool = False
    include_needs_review: bool = False

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Test title cannot be blank")
        return cleaned


class TestOut(BaseModel):
    """Public test metadata without answer keys or explanations."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    exam_config_id: UUID | None = None
    subject_code: str | None = None
    source_document_ids: list[UUID] = Field(default_factory=list)
    settings_json: dict[str, Any]
    total_questions: int
    max_score: Decimal
    status: str
    created_at: datetime
    latest_attempt_id: UUID | None = None
    latest_attempt_status: str | None = None


class TestListResponse(BaseModel):
    """Paginated list of user-created tests."""

    items: list[TestOut]
    total: int
    limit: int
    offset: int
