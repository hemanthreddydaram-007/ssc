from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ProvenanceType = Literal[
    "extracted",
    "paraphrased",
    "ai_explanation",
    "externally_verified",
    "unverified",
]

ReviewStatusType = Literal[
    "verified",
    "needs_review",
    "conflict",
    "rejected",
    "insufficient_evidence",
]


class SourceRefPayload(BaseModel):
    """Canonical source provenance reference attached to facts, concepts, and notes."""

    document_id: UUID | None = None
    page_number: int | None = None
    chunk_id: UUID | None = None
    section_title: str | None = None
    supporting_excerpt: str | None = None
    provenance: ProvenanceType = "extracted"


class QuestionVerificationResult(BaseModel):
    """Structured result returned by `LLMProvider.verify_question`."""

    is_valid: bool
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    suggested_correct_key: str | None = None
    reasoning: str = ""
