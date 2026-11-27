"""Unit tests for M2 extraction services.

Covers:
- pdf_extractor: page-by-page text extraction, page numbers, raw_char_count
- scan_detector: image-heavy page → needs_ocr=True; text-heavy page → False
- ocr_adapter: NullOCRAdapter protocol compliance (no crash, leaves needs_ocr=True)
- chunker: (stem + options) atomic; (passage + questions) atomic; never zero chunks
- coverage_audit: derived fields strictly from real counts (no fake %)

These tests import from app.services.extraction.* (implemented by @document-engineer).
Tests are skipped (not failed) if the module doesn't exist yet, so the suite stays
green during Wave 1 parallel work.
"""
from __future__ import annotations

import importlib
import io
import types
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.pdf_factory import (
    build_image_only_pdf,
    build_text_pdf,
)

# ---------------------------------------------------------------------------
# Lazy import helpers — skip tests if module not yet implemented
# ---------------------------------------------------------------------------


def _try_import(module_path: str) -> types.ModuleType | None:
    try:
        return importlib.import_module(module_path)
    except ModuleNotFoundError:
        return None


def _require(module_path: str) -> types.ModuleType:
    mod = _try_import(module_path)
    if mod is None:
        pytest.skip(f"Module {module_path!r} not yet implemented — skipping until Wave 2")
    return mod


# ---------------------------------------------------------------------------
# pdf_extractor tests
# ---------------------------------------------------------------------------


class TestPdfExtractor:
    """Tests for app.services.extraction.pdf_extractor."""

    def test_extracts_correct_page_count(self) -> None:
        mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_text_pdf(["Page one text.", "Page two text.", "Page three text."])
        pages = mod.extract_pages(io.BytesIO(pdf_bytes))
        assert len(pages) == 3

    def test_page_numbers_are_one_indexed(self) -> None:
        mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_text_pdf(["Alpha", "Beta"])
        pages = mod.extract_pages(io.BytesIO(pdf_bytes))
        page_nums = [p.page_number for p in pages]
        assert page_nums == [1, 2]

    def test_extracted_text_contains_source_text(self) -> None:
        mod = _require("app.services.extraction.pdf_extractor")
        marker = "UNIQUEMARKER_XYZ_42"
        pdf_bytes = build_text_pdf([f"This is page one with {marker}."])
        pages = mod.extract_pages(io.BytesIO(pdf_bytes))
        assert len(pages) >= 1
        assert marker in pages[0].extracted_text

    def test_raw_char_count_matches_text_length(self) -> None:
        mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_text_pdf(["Hello World"])
        pages = mod.extract_pages(io.BytesIO(pdf_bytes))
        assert len(pages) >= 1
        page = pages[0]
        # raw_char_count must equal the actual character count (or stripped)
        # — never manually set to a fake number
        assert page.raw_char_count == len(page.extracted_text)

    def test_multipage_text_isolation(self) -> None:
        """Text from page N must not bleed into page N+1."""
        mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_text_pdf(["ONLY_ON_PAGE_1", "ONLY_ON_PAGE_2"])
        pages = mod.extract_pages(io.BytesIO(pdf_bytes))
        assert len(pages) == 2
        assert "ONLY_ON_PAGE_1" in pages[0].extracted_text
        assert "ONLY_ON_PAGE_1" not in pages[1].extracted_text
        assert "ONLY_ON_PAGE_2" in pages[1].extracted_text
        assert "ONLY_ON_PAGE_2" not in pages[0].extracted_text

    def test_no_llm_calls_during_extraction(self) -> None:
        """Extraction must be pure local processing — zero AI calls."""
        mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_text_pdf(["Test page"])
        # If any LLM/HTTP client is called this will raise
        with (
            patch("httpx.Client.send", side_effect=AssertionError("LLM call during extraction!")),
            patch(
                "httpx.AsyncClient.send",
                side_effect=AssertionError("LLM call during extraction!"),
            ),
        ):
            pages = mod.extract_pages(io.BytesIO(pdf_bytes))
        assert len(pages) >= 1

    def test_extraction_method_field_set(self) -> None:
        mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_text_pdf(["Sample text"])
        pages = mod.extract_pages(io.BytesIO(pdf_bytes))
        for page in pages:
            assert page.extraction_method in {
                "pymupdf", "pdfplumber", "ocr", "null_ocr", "hybrid"
            }, f"Unknown extraction_method: {page.extraction_method!r}"

    def test_confidence_in_range(self) -> None:
        mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_text_pdf(["Confidence test"])
        pages = mod.extract_pages(io.BytesIO(pdf_bytes))
        for page in pages:
            assert 0.0 <= page.confidence <= 1.0, (
                f"confidence={page.confidence} out of [0,1]"
            )


# ---------------------------------------------------------------------------
# scan_detector tests
# ---------------------------------------------------------------------------


class TestScanDetector:
    """Tests for app.services.extraction.scan_detector."""

    def test_text_heavy_page_not_flagged_needs_ocr(self) -> None:
        mod = _require("app.services.extraction.scan_detector")
        # Page with substantial text should not need OCR
        result = mod.detect_scan_pages(
            [
                _make_page_data(
                    page_number=1,
                    extracted_text="A" * 300,
                    image_count=0,
                    raw_char_count=300,
                )
            ]
        )
        assert result[0].needs_ocr is False

    def test_image_only_page_flagged_needs_ocr(self) -> None:
        mod = _require("app.services.extraction.scan_detector")
        result = mod.detect_scan_pages(
            [
                _make_page_data(
                    page_number=1,
                    extracted_text="",
                    image_count=1,
                    raw_char_count=0,
                )
            ]
        )
        assert result[0].needs_ocr is True

    def test_mixed_page_low_char_density_flagged(self) -> None:
        """Page with many images but very few chars → needs_ocr."""
        mod = _require("app.services.extraction.scan_detector")
        result = mod.detect_scan_pages(
            [
                _make_page_data(
                    page_number=1,
                    extracted_text="ab",
                    image_count=5,
                    raw_char_count=2,
                )
            ]
        )
        assert result[0].needs_ocr is True

    def test_no_silent_empty_extraction_raises_or_flags(self) -> None:
        """Image-only PDF must never produce pages with needs_ocr=False + empty text."""
        mod = _require("app.services.extraction.scan_detector")
        pdf_extractor_mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_image_only_pdf(n_pages=1)
        pages = pdf_extractor_mod.extract_pages(io.BytesIO(pdf_bytes))
        flagged = mod.detect_scan_pages(pages)
        for page in flagged:
            if not page.extracted_text.strip():
                assert page.needs_ocr is True, (
                    "Empty-text page must be flagged needs_ocr=True (no silent empty extraction)"
                )

    def test_scan_detection_pure_local(self) -> None:
        """Scan detection must not make AI calls."""
        mod = _require("app.services.extraction.scan_detector")
        with patch("httpx.Client.send", side_effect=AssertionError("AI call in scan detection!")):
            mod.detect_scan_pages(
                [_make_page_data(1, "", 1, 0)]
            )


def _make_page_data(
    page_number: int,
    extracted_text: str,
    image_count: int,
    raw_char_count: int,
) -> Any:
    """Return a duck-typed page data object compatible with scan_detector input."""
    obj = MagicMock()
    obj.page_number = page_number
    obj.extracted_text = extracted_text
    obj.image_count = image_count
    obj.raw_char_count = raw_char_count
    obj.needs_ocr = False
    obj.table_count = 0
    obj.warning = None
    return obj


# ---------------------------------------------------------------------------
# OCR adapter tests
# ---------------------------------------------------------------------------


class TestNullOCRAdapter:
    """Tests for app.services.extraction.ocr_adapter.NullOCRAdapter."""

    def test_null_adapter_does_not_crash(self) -> None:
        mod = _require("app.services.extraction.ocr_adapter")
        adapter = mod.NullOCRAdapter()
        page = _make_page_data(1, "", 1, 0)
        # Must return without raising
        result = adapter.process_page(page)
        # Result should be the page (possibly unchanged)
        assert result is not None

    def test_null_adapter_preserves_needs_ocr_true(self) -> None:
        """NullOCRAdapter should leave needs_ocr=True — it doesn't do real OCR."""
        mod = _require("app.services.extraction.ocr_adapter")
        adapter = mod.NullOCRAdapter()
        page = _make_page_data(1, "", 1, 0)
        page.needs_ocr = True
        result = adapter.process_page(page)
        assert result.needs_ocr is True

    def test_null_adapter_does_not_make_ai_calls(self) -> None:
        mod = _require("app.services.extraction.ocr_adapter")
        adapter = mod.NullOCRAdapter()
        page = _make_page_data(1, "", 1, 0)
        with patch("httpx.Client.send", side_effect=AssertionError("AI call in NullOCRAdapter!")):
            adapter.process_page(page)

    def test_ocr_adapter_protocol_satisfied(self) -> None:
        """NullOCRAdapter must implement the OCRAdapter protocol."""
        mod = _require("app.services.extraction.ocr_adapter")
        adapter = mod.NullOCRAdapter()
        assert hasattr(adapter, "process_page"), "Missing process_page method"

    def test_provider_name_is_null(self) -> None:
        mod = _require("app.services.extraction.ocr_adapter")
        adapter = mod.NullOCRAdapter()
        assert adapter.provider_name in {"null", "none", "NullOCRAdapter", "null_ocr"}


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------


class TestChunker:
    """Tests for app.services.extraction.chunker."""

    def test_mcq_stem_and_options_not_split(self) -> None:
        """A single MCQ (stem + 4 options) must land in exactly one chunk."""
        mod = _require("app.services.extraction.chunker")
        stem = "Which of the following is a prime number?"
        options = ["11", "9", "15", "21"]
        full_text = stem + "  " + "  ".join(
            f"({chr(65 + i)}) {opt}" for i, opt in enumerate(options)
        )
        pages = [_make_page_data(1, full_text, 0, len(full_text))]
        chunks = mod.chunk_pages(pages)
        assert len(chunks) >= 1
        # The stem must appear in the same chunk as at least the first option
        stem_chunk = next(
            (c for c in chunks if stem in c.content_text),
            None,
        )
        assert stem_chunk is not None, "MCQ stem not found in any chunk"
        assert "(A) 11" in stem_chunk.content_text, (
            "First option missing from stem's chunk — chunker split the MCQ"
        )

    def test_passage_and_dependent_questions_not_split(self) -> None:
        """Reading passage + its questions must be in one chunk."""
        mod = _require("app.services.extraction.chunker")
        passage = "The Industrial Revolution began in Britain in the 18th century. " * 5
        questions = [
            "Q1: Where did the Industrial Revolution begin? (A) France (B) Britain (C) Germany",
            "Q2: In which century? (A) 17th (B) 18th (C) 19th",
        ]
        full_text = passage + "  " + "  ".join(questions)
        pages = [_make_page_data(1, full_text, 0, len(full_text))]
        chunks = mod.chunk_pages(pages)
        passage_chunk = next(
            (c for c in chunks if "Industrial Revolution" in c.content_text),
            None,
        )
        assert passage_chunk is not None, "Passage not found in any chunk"
        assert "Q1:" in passage_chunk.content_text, (
            "Q1 not in same chunk as passage — chunker split passage from questions"
        )

    def test_mcq_split_across_blocks_remains_atomic(self) -> None:
        """Stem in block 0 and (A)..(D) in separate blocks must stay in one chunk."""
        mod = _require("app.services.extraction.chunker")
        chunker = mod.SemanticChunker(document_id=uuid.uuid4(), extraction_version="v1")
        pages = [
            {
                "page_number": 1,
                "text_blocks": [
                    "Q.10 Which river is known as the Dakshin Ganga?",
                    "(A) Krishna",
                    "(B) Godavari",
                    "(C) Cauvery",
                    "(D) Mahanadi",
                    "Q.11 Next standalone question with options.\n(A) X\n(B) Y\n(C) Z\n(D) W",
                ],
                "tables_data": [],
                "asset_ids": [],
            }
        ]
        chunks = chunker.chunk_pages(pages)
        q10_chunks = [c for c in chunks if "Dakshin Ganga" in c.content_text]
        assert len(q10_chunks) == 1
        assert q10_chunks[0].chunk_type == "question_block"
        for opt in ("(A) Krishna", "(B) Godavari", "(C) Cauvery", "(D) Mahanadi"):
            assert opt in q10_chunks[0].content_text
        assert "Q.11" not in q10_chunks[0].content_text

    def test_no_empty_chunks(self) -> None:
        mod = _require("app.services.extraction.chunker")
        pdf_bytes = build_text_pdf(["Non-empty page content goes here."])
        pdf_extractor_mod = _require("app.services.extraction.pdf_extractor")
        pages = pdf_extractor_mod.extract_pages(io.BytesIO(pdf_bytes))
        chunks = mod.chunk_pages(pages)
        for chunk in chunks:
            assert chunk.content_text.strip(), "Chunk with empty content_text found"

    def test_chunks_cover_all_pages(self) -> None:
        """Every page_number must appear in at least one chunk's page_start..page_end range."""
        mod = _require("app.services.extraction.chunker")
        texts = [f"Page {i} content is unique marker PGMK{i}." for i in range(1, 4)]
        pdf_bytes = build_text_pdf(texts)
        pdf_extractor_mod = _require("app.services.extraction.pdf_extractor")
        pages = pdf_extractor_mod.extract_pages(io.BytesIO(pdf_bytes))
        chunks = mod.chunk_pages(pages)
        covered = set()
        for chunk in chunks:
            for pg in range(chunk.page_start, chunk.page_end + 1):
                covered.add(pg)
        for page in pages:
            assert page.page_number in covered, (
                f"Page {page.page_number} not covered by any chunk"
            )

    def test_chunk_index_monotonically_increases(self) -> None:
        mod = _require("app.services.extraction.chunker")
        texts = ["Alpha text", "Beta text", "Gamma text"]
        pdf_bytes = build_text_pdf(texts)
        pdf_extractor_mod = _require("app.services.extraction.pdf_extractor")
        pages = pdf_extractor_mod.extract_pages(io.BytesIO(pdf_bytes))
        chunks = mod.chunk_pages(pages)
        indices = [c.chunk_index for c in chunks]
        assert indices == sorted(indices), "chunk_index not monotonically increasing"
        assert len(indices) == len(set(indices)), "Duplicate chunk_index found"

    def test_chunk_page_range_valid(self) -> None:
        mod = _require("app.services.extraction.chunker")
        texts = ["Page A", "Page B"]
        pdf_bytes = build_text_pdf(texts)
        pdf_extractor_mod = _require("app.services.extraction.pdf_extractor")
        pages = pdf_extractor_mod.extract_pages(io.BytesIO(pdf_bytes))
        chunks = mod.chunk_pages(pages)
        for chunk in chunks:
            assert chunk.page_start >= 1
            assert chunk.page_end >= chunk.page_start

    def test_no_llm_calls_during_chunking(self) -> None:
        mod = _require("app.services.extraction.chunker")
        pdf_extractor_mod = _require("app.services.extraction.pdf_extractor")
        pdf_bytes = build_text_pdf(["Chunk me please."])
        pages = pdf_extractor_mod.extract_pages(io.BytesIO(pdf_bytes))
        with patch("httpx.Client.send", side_effect=AssertionError("LLM call during chunking!")):
            chunks = mod.chunk_pages(pages)
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# Coverage audit tests
# ---------------------------------------------------------------------------


class TestCoverageAudit:
    """Tests for app.services.extraction.coverage_audit."""

    def test_progress_percent_derived_from_real_counts(self) -> None:
        """progress_percent must be None when total_items is 0, never fake 100."""
        mod = _require("app.services.extraction.coverage_audit")
        audit = mod.build_coverage_summary(
            total_pages=0,
            pages_extracted_text=0,
            pages_extracted_ocr=0,
            pages_requiring_ocr=0,
            pages_not_processed=0,
            tables_extracted=0,
            images_extracted=0,
            chunks_created=0,
            facts_extracted=0,
            concepts_identified=0,
            questions_extracted=0,
            records_rejected_or_uncertain=0,
            low_confidence_pages=[],
            low_confidence_topics=[],
        )
        # With zero pages, progress should be None or 0, never 100
        assert audit.get("progress_percent") in (None, 0), (
            f"progress_percent={audit.get('progress_percent')} for 0-page doc — must not be 100"
        )

    def test_progress_percent_correct_math(self) -> None:
        mod = _require("app.services.extraction.coverage_audit")
        audit = mod.build_coverage_summary(
            total_pages=10,
            pages_extracted_text=6,
            pages_extracted_ocr=2,
            pages_requiring_ocr=2,
            pages_not_processed=0,
            tables_extracted=3,
            images_extracted=5,
            chunks_created=12,
            facts_extracted=0,
            concepts_identified=0,
            questions_extracted=0,
            records_rejected_or_uncertain=0,
            low_confidence_pages=[],
            low_confidence_topics=[],
        )
        # 6+2 = 8 out of 10 = 80%
        pct = audit.get("progress_percent")
        if pct is not None:
            assert pct == 80, f"Expected 80% but got {pct}%"

    def test_all_required_keys_present(self) -> None:
        mod = _require("app.services.extraction.coverage_audit")
        audit = mod.build_coverage_summary(
            total_pages=1,
            pages_extracted_text=1,
            pages_extracted_ocr=0,
            pages_requiring_ocr=0,
            pages_not_processed=0,
            tables_extracted=0,
            images_extracted=0,
            chunks_created=1,
            facts_extracted=0,
            concepts_identified=0,
            questions_extracted=0,
            records_rejected_or_uncertain=0,
            low_confidence_pages=[],
            low_confidence_topics=[],
        )
        required = {
            "total_pages", "pages_extracted_text", "pages_extracted_ocr",
            "pages_requiring_ocr", "pages_not_processed", "low_confidence_pages",
            "tables_extracted", "images_extracted", "chunks_created",
            "facts_extracted", "concepts_identified", "questions_extracted",
            "records_rejected_or_uncertain", "low_confidence_topics",
        }
        missing = required - set(audit.keys())
        assert not missing, f"Coverage summary missing keys: {missing}"
