from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.ai.gemini_provider import sanitize_text_for_llm
from app.models.document import DocumentChunk

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_excerpt(text: str) -> str:
    """Collapse whitespace and lowercase text for deterministic excerpt comparison."""
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def _matches_page_text(excerpt_norm: str, page_text_norm: str) -> bool:
    if not excerpt_norm or not page_text_norm:
        return False
    if excerpt_norm in page_text_norm:
        return True
    if len(excerpt_norm) >= 16:
        return fuzz.partial_ratio(excerpt_norm, page_text_norm) >= 82.0
    # Short excerpts require exact word-boundary or high token overlap
    return fuzz.token_set_ratio(excerpt_norm, page_text_norm) >= 90.0


@dataclass(frozen=True, slots=True)
class GroundingResult:
    """Outcome of deterministic page and excerpt verification."""

    resolved_page_number: int | None
    supporting_excerpt: str | None
    provenance: str
    review_status: str
    is_grounded: bool


def verify_grounding(
    pages_by_num: dict[int, str],
    *,
    claimed_page: int | None,
    page_start: int,
    page_end: int,
    supporting_excerpt: str | None,
    claimed_provenance: str,
    confidence: float,
) -> GroundingResult:
    """Verify claimed page citation and excerpt against persisted `DocumentPage` text."""
    excerpt_clean = (supporting_excerpt or "").strip()
    excerpt_norm = normalize_excerpt(excerpt_clean)

    # 1. Check the claimed page first if it exists in this document.
    if claimed_page is not None and claimed_page in pages_by_num:
        page_norm = normalize_excerpt(pages_by_num[claimed_page])
        if excerpt_norm and _matches_page_text(excerpt_norm, page_norm):
            status = (
                "verified"
                if claimed_provenance in ("extracted", "paraphrased") and confidence >= 0.65
                else "needs_review"
            )
            return GroundingResult(
                resolved_page_number=claimed_page,
                supporting_excerpt=excerpt_clean,
                provenance=claimed_provenance,
                review_status=status,
                is_grounded=True,
            )

    # 2. Scan the chunk's page span to correct page-number drift on multi-page chunks.
    if excerpt_norm:
        for page_num in range(page_start, page_end + 1):
            if page_num not in pages_by_num:
                continue
            page_norm = normalize_excerpt(pages_by_num[page_num])
            if _matches_page_text(excerpt_norm, page_norm):
                status = (
                    "verified"
                    if claimed_provenance in ("extracted", "paraphrased") and confidence >= 0.65
                    else "needs_review"
                )
                return GroundingResult(
                    resolved_page_number=page_num,
                    supporting_excerpt=excerpt_clean,
                    provenance=claimed_provenance,
                    review_status=status,
                    is_grounded=True,
                )

    # 3. Never retain an out-of-bounds / unverified page citation as verified.
    valid_page = (
        claimed_page if (claimed_page is not None and claimed_page in pages_by_num) else None
    )
    if valid_page is None and page_start == page_end and page_start in pages_by_num:
        valid_page = page_start

    effective_provenance = (
        "unverified" if claimed_provenance == "extracted" else claimed_provenance
    )
    return GroundingResult(
        resolved_page_number=valid_page,
        supporting_excerpt=excerpt_clean or None,
        provenance=effective_provenance,
        review_status="needs_review",
        is_grounded=False,
    )


def format_chunk_with_page_markers(
    chunk: DocumentChunk, pages_by_num: dict[int, str]
) -> str:
    """Ensure chunk text carries explicit `[PAGE N]` markers for accurate citations."""
    text = sanitize_text_for_llm(chunk.content_text or "")
    if "[PAGE " in text:
        return text
    if chunk.page_start == chunk.page_end:
        return f"[PAGE {chunk.page_start}]\n{text}"

    # Multi-page chunk without embedded markers: supply page-delimited source text when small.
    delimited_parts: list[str] = []
    for p_num in range(chunk.page_start, chunk.page_end + 1):
        p_text = sanitize_text_for_llm(pages_by_num.get(p_num, "")).strip()
        if p_text:
            delimited_parts.append(f"[PAGE {p_num}]\n{p_text}")
    return "\n\n".join(delimited_parts) if delimited_parts else f"[PAGE {chunk.page_start}]\n{text}"
