"""Semantic chunker that preserves question-option groups and passage+questions.

Rules:
- Never split a question stem from its (A)-(D) options.
- Never split a comprehension/DI passage from the questions that reference it.
- Respect heading/section boundaries as natural chunk boundaries.
- Respect table boundaries (each table block is its own chunk).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

# Regexes for detecting question starts in multi-choice formats
QUESTION_STEM_RE = re.compile(
    r"^\s*(?:Q\.?\s*\d+[.:)]?|\d+[.)])\s+.{5,}", re.MULTILINE
)
OPTION_LINE_RE = re.compile(
    r"^\s*\(?(?:[Aa]|[Bb]|[Cc]|[Dd]|[1-4])[.)]\s+\S", re.MULTILINE
)
HEADING_RE = re.compile(r"^#{1,4}\s+\S|^[A-Z][A-Z\s]{4,}$", re.MULTILINE)
PASSAGE_INTRO_RE = re.compile(
    r"(?:passage|read the following|directions for questions|based on the following)",
    re.IGNORECASE,
)


@dataclass
class ChunkRecord:
    """A semantic document chunk ready for DB persistence."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    document_id: uuid.UUID = field(default_factory=uuid.uuid4)
    chunk_index: int = 0
    page_start: int = 1
    page_end: int = 1
    section_title: str | None = None
    chunk_type: str = "prose"  # prose|question_block|passage_group|table|mixed
    content_text: str = ""
    asset_ids_json: list[str] = field(default_factory=list)
    subject_hint: str | None = None
    topic_hint: str | None = None
    extraction_version: str = "v1"
    token_estimate: int = 0


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars/token for English/Hindi text."""
    return max(1, len(text) // 4)


class SemanticChunker:
    """Breaks page-level text into semantic chunks respecting MCQ/passage boundaries."""

    MAX_CHUNK_TOKENS = 1500  # target upper bound before forced split

    def __init__(self, document_id: uuid.UUID, extraction_version: str = "v1") -> None:
        self.document_id = document_id
        self.extraction_version = extraction_version

    def chunk_pages(
        self,
        pages: list[Any],  # list of dicts or ExtractedPage-like objects
    ) -> list[ChunkRecord]:
        """Convert extracted pages into semantic chunks."""
        chunks: list[ChunkRecord] = []
        chunk_index = 0

        # Collect all text blocks with page attribution
        all_blocks: list[dict[str, Any]] = []
        for page in pages:
            if isinstance(page, dict):
                page_number = page["page_number"]
                text_blocks = page.get("text_blocks", [])
                tables_data = page.get("tables_data", [])
                asset_ids = page.get("asset_ids", [])
            else:
                page_number = page.page_number
                raw_text = getattr(page, "extracted_text", "") or ""
                raw_blocks = getattr(page, "text_blocks", None)
                if isinstance(raw_blocks, (list, tuple)):
                    text_blocks = list(raw_blocks)
                else:
                    text_blocks = [b.strip() for b in raw_text.split("\n\n") if b.strip()]
                raw_tables = getattr(page, "tables_data", None)
                tables_data = list(raw_tables) if isinstance(raw_tables, (list, tuple)) else []
                raw_assets = getattr(page, "asset_ids", None)
                asset_ids = list(raw_assets) if isinstance(raw_assets, (list, tuple)) else []

            for tb in text_blocks:
                if tb.strip():
                    all_blocks.append(
                        {"text": tb.strip(), "page": page_number, "type": "text"}
                    )
            for table in tables_data:
                table_text = self._table_to_text(table)
                if table_text:
                    all_blocks.append(
                        {"text": table_text, "page": page_number, "type": "table"}
                    )
            for asset_id in asset_ids:
                if all_blocks:
                    if "asset_ids" not in all_blocks[-1]:
                        all_blocks[-1]["asset_ids"] = []
                    all_blocks[-1]["asset_ids"].append(str(asset_id))

        # Group into semantic chunks
        current: list[dict[str, Any]] = []
        current_type = "prose"
        current_page_start = 1

        def flush_chunk() -> None:
            nonlocal chunk_index, current, current_type, current_page_start
            if not current:
                return
            combined_text = "\n\n".join(b["text"] for b in current)
            asset_ids: list[str] = []
            for b in current:
                asset_ids.extend(b.get("asset_ids", []))
            page_start = current[0]["page"]
            page_end = current[-1]["page"]
            chunks.append(
                ChunkRecord(
                    document_id=self.document_id,
                    chunk_index=chunk_index,
                    page_start=page_start,
                    page_end=page_end,
                    chunk_type=current_type,
                    content_text=combined_text,
                    asset_ids_json=asset_ids,
                    extraction_version=self.extraction_version,
                    token_estimate=_estimate_tokens(combined_text),
                )
            )
            chunk_index += 1
            current = []
            current_type = "prose"

        i = 0
        while i < len(all_blocks):
            block = all_blocks[i]
            text = block["text"]
            block_type = block["type"]

            if block_type == "table":
                # Tables always flush previous and become their own chunk
                flush_chunk()
                current = [block]
                current_type = "table"
                flush_chunk()
                i += 1
                continue

            # Detect passage + questions group
            if PASSAGE_INTRO_RE.search(text):
                flush_chunk()
                passage_group = [block]
                i += 1
                # Absorb subsequent question blocks that belong to this passage
                while i < len(all_blocks):
                    next_block = all_blocks[i]
                    if next_block["type"] == "table":
                        break
                    next_text = next_block["text"]
                    # Stop if we hit a new passage or heading
                    if PASSAGE_INTRO_RE.search(next_text) or HEADING_RE.search(next_text):
                        break
                    passage_group.append(next_block)
                    i += 1
                current = passage_group
                current_type = "passage_group"
                flush_chunk()
                continue

            # Detect question block (stem + options)
            if QUESTION_STEM_RE.search(text) and OPTION_LINE_RE.search(text):
                # Question with options in same block — treat as atomic question_block
                flush_chunk()
                current = [block]
                current_type = "question_block"
                flush_chunk()
                i += 1
                continue

            # Detect multi-block MCQ: stem on this block, options on next block(s)
            if QUESTION_STEM_RE.search(text):
                flush_chunk()
                q_group = [block]
                i += 1
                # Absorb option lines for this question (up to 4 option lines)
                options_found = 0
                while i < len(all_blocks) and options_found < 4:
                    next_block = all_blocks[i]
                    if next_block["type"] == "table":
                        break
                    next_text = next_block["text"]
                    if OPTION_LINE_RE.match(next_text):
                        q_group.append(next_block)
                        options_found += 1
                        i += 1
                    elif QUESTION_STEM_RE.search(next_text):
                        break
                    else:
                        # Could be an explanation or multi-line option
                        q_group.append(next_block)
                        i += 1
                        if QUESTION_STEM_RE.search(next_text):
                            break
                current = q_group
                current_type = "question_block"
                flush_chunk()
                continue

            # Heading → flush and start new prose chunk
            if HEADING_RE.search(text):
                flush_chunk()
                current = [block]
                current_type = "prose"
                i += 1
                continue

            # Regular prose — accumulate, flushing if size limit exceeded
            current.append(block)
            token_estimate = sum(_estimate_tokens(b["text"]) for b in current)
            if token_estimate > self.MAX_CHUNK_TOKENS:
                flush_chunk()
            i += 1

        flush_chunk()
        return chunks

    @staticmethod
    def _table_to_text(table: list[list[str | None]]) -> str:
        """Convert a 2D table to pipe-delimited Markdown text."""
        if not table:
            return ""
        rows = []
        for row in table:
            cells = " | ".join(str(c) if c is not None else "" for c in row)
            rows.append(f"| {cells} |")
        if len(rows) > 1:
            sep = "| " + " | ".join("---" for _ in table[0]) + " |"
            rows.insert(1, sep)
        return "\n".join(rows)


def chunk_pages(
    pages: list[Any],
    *,
    document_id: uuid.UUID | None = None,
    extraction_version: str = "v1",
) -> list[ChunkRecord]:
    """Convenience helper to chunk a list of pages without instantiating SemanticChunker."""
    chunker = SemanticChunker(
        document_id=document_id or uuid.uuid4(),
        extraction_version=extraction_version,
    )
    return chunker.chunk_pages(pages)
