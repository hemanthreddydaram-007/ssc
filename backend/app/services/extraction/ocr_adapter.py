"""OCR adapter protocol and default NullOCRAdapter.

The NullOCRAdapter is used when no OCR provider is configured (default in M2).
In M3+, the GeminiVisionOCRAdapter delegates to @learning-engineer's LLMProvider.
An optional RapidOCRAdapter (pure-Python via onnxruntime) can also be plugged in
without any native Tesseract installation on Windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class OCRPageResult:
    """Result of OCR processing a single page image."""

    page_number: int
    extracted_text: str
    confidence: float
    ocr_provider: str
    warning: str | None = None


@runtime_checkable
class OCRAdapter(Protocol):
    """Replaceable OCR/vision adapter interface."""

    def extract_page(
        self,
        image_bytes: bytes,
        mime_type: str,
        page_number: int,
        language_hint: str = "en",
    ) -> OCRPageResult: ...


@dataclass
class NullOCRAdapter:
    """Default no-op adapter: marks pages as needing OCR with an actionable warning.

    Used in M2 dev/test mode so the system never silently produces empty extracted
    text. Any page that requires OCR is left with a clear warning message rather
    than falsely appearing as successfully extracted with zero content.
    """

    provider_name: str = "null"
    _warnings: list[str] = field(default_factory=list)

    def process_page(self, page: Any) -> Any:
        """Mark a page object as still requiring OCR with an actionable warning."""
        page_num = getattr(page, "page_number", 1)
        page.needs_ocr = True
        page.warning = (
            f"Page {page_num}: OCR required but no OCR provider is configured."
        )
        return page

    def extract_page(
        self,
        image_bytes: bytes,
        mime_type: str,
        page_number: int,
        language_hint: str = "en",
    ) -> OCRPageResult:
        warning = (
            f"Page {page_number}: OCR required but no OCR provider is configured. "
            "Configure GEMINI_API_KEY and use GeminiVisionOCRAdapter to extract this page."
        )
        self._warnings.append(warning)
        return OCRPageResult(
            page_number=page_number,
            extracted_text="",
            confidence=0.0,
            ocr_provider="null",
            warning=warning,
        )
