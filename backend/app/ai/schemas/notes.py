from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.schemas.common import ProvenanceType, ReviewStatusType

NoteTypeLiteral = Literal["detailed", "quick_revision", "formula_sheet", "strategy_sheet"]

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


class NoteBlockMetadataItem(BaseModel):
    """Typed key-value metadata item compatible with Gemini JSON schema."""

    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1)


class GeneratedSourceRefItem(BaseModel):
    """Source citation returned by LLM referencing a supplied document page."""

    page_number: int | None = None
    supporting_excerpt: str = ""


class GeneratedNoteBlock(BaseModel):
    """Single structured block inside a generated note section."""

    block_type: NoteBlockType = "concept"
    title: str | None = None
    body: str = Field(min_length=1)
    formula_latex: str | None = None
    metadata_items: list[NoteBlockMetadataItem] = Field(default_factory=list)
    provenance: ProvenanceType = "ai_explanation"
    source_refs: list[GeneratedSourceRefItem] = Field(default_factory=list)
    review_status: ReviewStatusType = "verified"


class GeneratedNoteSection(BaseModel):
    """Section grouping structured blocks inside a note."""

    key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    blocks: list[GeneratedNoteBlock] = Field(default_factory=list)


class GeneratedNoteOutput(BaseModel):
    """Structured LLM output for detailed, quick-revision, formula, or strategy notes."""

    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1)
    sections: list[GeneratedNoteSection] = Field(default_factory=list)
    one_minute_recap: str | None = None
