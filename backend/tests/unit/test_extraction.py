from __future__ import annotations

import io
import uuid
from pathlib import Path

import pymupdf
from PIL import Image

from app.services.extraction import (
    NullOCRAdapter,
    PDFExtractor,
    SemanticChunker,
    classify_page,
    is_garbled_text,
)


def test_scan_detector_classifies_text_scanned_image_heavy_and_garbled_pages() -> None:
    needs_ocr, warning = classify_page(
        raw_char_count=240,
        image_count=0,
        image_area_ratio=0.0,
        text="SSC CHSL Tier 1 Quantitative Aptitude study notes on percentages and ratios.",
    )
    assert needs_ocr is False
    assert warning is None

    scanned, scanned_warn = classify_page(raw_char_count=8, image_count=1, image_area_ratio=0.8)
    assert scanned is True
    assert scanned_warn is not None
    assert "OCR" in scanned_warn

    empty_page, empty_warn = classify_page(raw_char_count=0, image_count=0)
    assert empty_page is True
    assert empty_warn is not None

    img_heavy, img_warn = classify_page(raw_char_count=65, image_count=1, image_area_ratio=0.72)
    assert img_heavy is True
    assert img_warn is not None

    garbled_text = "".join(chr(0xE001 + (i % 20)) for i in range(80)) + "abc"
    garbled_flag, ratio = is_garbled_text(garbled_text)
    assert garbled_flag is True
    assert ratio > 0.30
    needs_garbled, garbled_warn = classify_page(
        raw_char_count=83, image_count=0, text=garbled_text
    )
    assert needs_garbled is True
    assert garbled_warn is not None and "garbled" in garbled_warn.lower()


def test_semantic_chunker_preserves_mcq_passage_and_table_boundaries() -> None:
    doc_id = uuid.uuid4()
    chunker = SemanticChunker(document_id=doc_id, extraction_version="v1")

    pages = [
        {
            "page_number": 1,
            "text_blocks": [
                "PERCENTAGES OVERVIEW",
                "A percentage expresses a fraction of 100 and is widely used in profit and loss.",
                "Q.1 If 20% of a number is 40, what is 50% of that number?\n"
                "(A) 80\n(B) 100\n(C) 120\n(D) 150",
                "Q.2 Find the ratio of 25 to 125.",
                "(A) 1:4",
                "(B) 1:5",
                "(C) 1:6",
                "(D) 1:8",
                "Directions for questions 3 to 4: Read the following passage carefully.\n"
                "Inflation affects purchasing power across sectors.",
                "Q.3 What does inflation reduce?\n"
                "(A) Purchasing power\n(B) Population\n(C) Rainfall\n(D) Gravity",
            ],
            "tables_data": [
                [["Fraction", "Percentage"], ["1/4", "25%"], ["1/5", "20%"]],
            ],
            "asset_ids": ["11111111-1111-1111-1111-111111111111"],
        }
    ]

    chunks = chunker.chunk_pages(pages)
    types = [c.chunk_type for c in chunks]
    assert "prose" in types
    assert "question_block" in types
    assert "passage_group" in types
    assert "table" in types

    q_blocks = [c for c in chunks if c.chunk_type == "question_block"]
    assert len(q_blocks) == 2
    assert "Q.1 If 20%" in q_blocks[0].content_text
    assert "(D) 150" in q_blocks[0].content_text
    assert "Q.2 Find the ratio" in q_blocks[1].content_text
    assert "(D) 1:8" in q_blocks[1].content_text

    passage_blocks = [c for c in chunks if c.chunk_type == "passage_group"]
    assert len(passage_blocks) == 1
    assert "Read the following passage" in passage_blocks[0].content_text
    assert "Q.3 What does inflation reduce?" in passage_blocks[0].content_text

    table_blocks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_blocks) == 1
    assert "| Fraction | Percentage |" in table_blocks[0].content_text


def test_null_ocr_adapter_never_fakes_success() -> None:
    adapter = NullOCRAdapter()
    result = adapter.extract_page(b"fake-png", "image/png", page_number=3, language_hint="en")
    assert result.page_number == 3
    assert result.extracted_text == ""
    assert result.confidence == 0.0
    assert result.ocr_provider == "null"
    assert result.warning is not None and "Page 3" in result.warning


def test_pdf_extractor_multicolumn_reading_order_and_diagram_cropping(tmp_path: Path) -> None:
    pdf_path = tmp_path / "multicolumn_diagram.pdf"
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=595, height=842)
        # Left column items (x=50), placed vertically separated from right column (x=330)
        page.insert_text((50, 120), "Q.1 Left column first question with sufficient text length.")
        page.insert_text((50, 220), "Q.2 Left column second question placed below Q.1.")
        # Right column items (x=330) at same y heights
        page.insert_text((330, 120), "Q.3 Right column third question read after left column.")
        page.insert_text((330, 220), "Q.4 Right column fourth question at bottom right.")
        # Vector geometry diagram
        shape = page.new_shape()
        shape.draw_rect(pymupdf.Rect(80, 320, 220, 440))
        shape.draw_line((80, 440), (220, 320))
        shape.finish(color=(0, 0, 0), width=1.5)
        shape.commit()
        pdf_path.write_bytes(doc.tobytes())
    finally:
        doc.close()

    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    extractor = PDFExtractor(storage_root=tmp_path, document_id=doc_id, user_id=user_id)
    pages = extractor.extract_all_pages(pdf_path, source_type="pdf")

    assert len(pages) == 1
    p1 = pages[0]
    assert p1.needs_ocr is False
    combined = "\n".join(p1.text_blocks)
    assert (
        combined.index("Q.1")
        < combined.index("Q.2")
        < combined.index("Q.3")
        < combined.index("Q.4")
    )
    assert len(p1.diagram_storage_keys) >= 1
    for key in p1.diagram_storage_keys:
        assert (tmp_path / key).is_file()


def test_pdf_extractor_flags_scanned_pdf_and_image_files_for_ocr(tmp_path: Path) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (180, 180), color=(240, 240, 240)).save(buf, format="PNG")
    img_bytes = buf.getvalue()

    img_path = tmp_path / "scan.png"
    img_path.write_bytes(img_bytes)

    scanned_pdf_path = tmp_path / "scanned.pdf"
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=400, height=400)
        page.insert_image(pymupdf.Rect(20, 20, 380, 380), stream=img_bytes)
        scanned_pdf_path.write_bytes(doc.tobytes())
    finally:
        doc.close()

    extractor = PDFExtractor(
        storage_root=tmp_path,
        document_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )

    pdf_pages = extractor.extract_all_pages(scanned_pdf_path, source_type="pdf")
    assert len(pdf_pages) == 1
    assert pdf_pages[0].needs_ocr is True
    assert pdf_pages[0].page_render_bytes is not None
    assert pdf_pages[0].image_count == 1
    assert pdf_pages[0].warning is not None

    img_pages = extractor.extract_all_pages(img_path, source_type="image")
    assert len(img_pages) == 1
    assert img_pages[0].needs_ocr is True
    assert img_pages[0].page_render_bytes == img_bytes
    assert len(img_pages[0].asset_records) == 1
