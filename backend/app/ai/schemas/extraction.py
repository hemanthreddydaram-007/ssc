from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.schemas.classification import SubjectCode

FactType = Literal[
    "date",
    "person",
    "place",
    "formula",
    "definition",
    "event",
    "rule",
    "statistic",
    "vocabulary",
    "shortcut",
    "other",
]


class PYQMetadataItem(BaseModel):
    """Typed PYQ metadata suitable for Gemini JSON schema constraints."""

    year: int | None = None
    shift: str | None = None
    exam_tier: str | None = None
    question_number: str | None = None


class ExtractedFactItem(BaseModel):
    """Fact, formula, date, or rule extracted from a document chunk."""

    fact_type: FactType = "definition"
    content: str = Field(min_length=1)
    topic_name: str | None = None
    source_page_number: int | None = None
    supporting_excerpt: str = ""
    provenance: Literal["extracted", "paraphrased", "unverified"] = "extracted"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    is_time_sensitive: bool = False
    source_date_label: str | None = None


class ExtractedConceptItem(BaseModel):
    """Concept record extracted from a document chunk."""

    title: str = Field(min_length=1, max_length=255)
    explanation: str = Field(min_length=1)
    topic_name: str | None = None
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    prerequisites: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    source_page_number: int | None = None
    supporting_excerpt: str = ""
    provenance: Literal["extracted", "paraphrased", "ai_explanation", "unverified"] = "paraphrased"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class ExtractedOptionItem(BaseModel):
    """Choice item for an extracted MCQ candidate."""

    key: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1)


class ExtractedQuestionItem(BaseModel):
    """Question candidate extracted from a document chunk."""

    question_text: str = Field(min_length=1)
    question_type: str = "single_choice"
    subject_code: SubjectCode = "unknown"
    topic_name: str | None = None
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    options: list[ExtractedOptionItem] = Field(default_factory=list)
    correct_option_key: str | None = None
    explanation: str = ""
    source_page_number: int | None = None
    supporting_excerpt: str = ""
    answer_key_provenance: Literal[
        "source_answer_key", "ai_solved", "user_supplied", "unverified"
    ] = "source_answer_key"
    pyq_metadata: PYQMetadataItem | None = None
    passage_text: str | None = None


class ChunkExtractionOutput(BaseModel):
    """Top-level structured output returned by chunk knowledge extraction."""

    detected_subject_code: SubjectCode = "unknown"
    topic_names: list[str] = Field(default_factory=list)
    facts: list[ExtractedFactItem] = Field(default_factory=list)
    concepts: list[ExtractedConceptItem] = Field(default_factory=list)
    questions: list[ExtractedQuestionItem] = Field(default_factory=list)
