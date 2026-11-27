from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExamConfigCreateRequest(BaseModel):
    """Payload to register a new exam configuration pack."""

    exam_code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=160)
    version: str = Field(default="1.0", min_length=1, max_length=32)
    config_json: dict[str, Any] = Field(default_factory=dict)
    source_url: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class ExamConfigOut(BaseModel):
    """Public representation of a versioned exam configuration pack."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exam_code: str
    name: str
    version: str
    config_json: dict[str, Any]
    source_url: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    created_at: datetime


class ExamConfigListResponse(BaseModel):
    """List envelope for available exam configurations."""

    items: list[ExamConfigOut]
    total: int
