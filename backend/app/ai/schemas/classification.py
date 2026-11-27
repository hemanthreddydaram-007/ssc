from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SubjectCode = Literal[
    "quantitative_aptitude",
    "reasoning",
    "english",
    "general_awareness",
    "unknown",
]

MaterialType = Literal[
    "notes",
    "textbook",
    "pyq_paper",
    "question_bank",
    "current_affairs",
    "other",
]


class DocumentClassificationOutput(BaseModel):
    """Structured LLM output for classifying a document or chunk."""

    subject_code: SubjectCode = "unknown"
    material_type: MaterialType = "other"
    language: str = Field(default="en", min_length=2, max_length=32)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    topic_candidates: list[str] = Field(default_factory=list)
    rationale: str = ""
