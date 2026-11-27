"""Scan and garbled-text detection utilities (standalone, testable without I/O)."""

from __future__ import annotations

import unicodedata
from typing import Any

MIN_TEXT_CHARS = 50
MAX_IMAGE_AREA_RATIO = 0.65
GARBLED_RATIO_THRESHOLD = 0.30


def is_garbled_text(text: str) -> tuple[bool, float]:
    """Return (is_garbled, ratio) for a page's extracted text."""
    if not text:
        return True, 1.0
    non_printable = sum(
        1
        for c in text
        if unicodedata.category(c) in {"Cc", "Cf", "Cs", "Co", "Cn"}
        or (0xE000 <= ord(c) <= 0xF8FF)  # Unicode Private Use Area (CID fonts)
    )
    ratio = non_printable / len(text)
    return ratio > GARBLED_RATIO_THRESHOLD, ratio


def classify_page(
    *,
    raw_char_count: int,
    image_count: int,
    image_area_ratio: float = 0.0,
    text: str = "",
) -> tuple[bool, str | None]:
    """Classify whether a page needs OCR and why.

    Returns (needs_ocr, warning_message | None).
    """
    if raw_char_count < MIN_TEXT_CHARS:
        if image_count > 0 or image_area_ratio > 0.1:
            return (
                True,
                (
                    f"Page has only {raw_char_count} chars with {image_count} images; "
                    "likely scanned — OCR required"
                ),
            )
        if raw_char_count == 0:
            return True, "Page has no extractable text; OCR required"

    if image_area_ratio > MAX_IMAGE_AREA_RATIO and raw_char_count < MIN_TEXT_CHARS * 2:
        return True, "Page is predominantly image content; OCR required"

    if text:
        garbled, ratio = is_garbled_text(text)
        if garbled:
            return (
                True,
                (
                    f"Page text appears garbled "
                    f"(CID/PUA ratio {ratio:.1%}); likely legacy font encoding — OCR required"
                ),
            )

    return False, None


def detect_scan_pages(pages: list[Any]) -> list[Any]:
    """Evaluate a sequence of extracted page objects and set `needs_ocr`/`warning` in place."""
    for page in pages:
        text = getattr(page, "extracted_text", "") or ""
        raw_chars = getattr(page, "raw_char_count", len(text))
        image_count = getattr(page, "image_count", 0)
        needs_ocr, warning = classify_page(
            raw_char_count=raw_chars,
            image_count=image_count,
            text=text,
        )
        page.needs_ocr = needs_ocr
        if warning is not None:
            page.warning = warning
    return pages
