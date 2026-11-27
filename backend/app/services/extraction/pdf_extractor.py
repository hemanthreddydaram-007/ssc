"""Multi-column-aware PDF and image extraction with table and diagram detection.

Strategy:
1. Use PyMuPDF for fast page-by-page text extraction with column-clustering for
   multi-column SSC PYQ layouts, raster image extraction, and vector drawing detection.
2. Use pdfplumber (optional) to supplement with structured table extraction.
3. Detect scanned / garbled pages via `scan_detector.classify_page` and flag them for OCR.
4. Crop and store embedded images and detected diagram regions as DocumentAssets.
"""

from __future__ import annotations

import io
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image

from app.services.extraction.scan_detector import classify_page

logger = logging.getLogger(__name__)

# --- Thresholds ---------------------------------------------------------
DIAGRAM_MIN_AREA_PX = 400  # minimum bbox area (px^2) for a drawing to become an asset
OCR_RENDER_DPI = 150  # used for page-to-image renders for OCR
HEADER_FOOTER_Y_PERCENT = 0.06


@dataclass
class ExtractedPage:
    """All extraction outputs for a single PDF or image page."""

    page_number: int  # 1-based
    text_blocks: list[str]
    tables_data: list[list[list[str | None]]]  # list of tables (rows x cols)
    image_storage_keys: list[str]  # paths relative to storage root (embedded images)
    diagram_storage_keys: list[str]  # cropped rendering of vector drawing regions
    asset_records: list[dict[str, Any]]  # dicts ready for DocumentAsset creation
    raw_char_count: int
    image_count: int
    table_count: int
    needs_ocr: bool
    warning: str | None
    extraction_method: str = "pymupdf"
    confidence: float = 1.0
    page_render_bytes: bytes | None = None  # full-page PNG for OCR if needed

    @property
    def extracted_text(self) -> str:
        """Combined page text blocks."""
        return "\n\n".join(self.text_blocks)


@dataclass
class PDFExtractor:
    """Extracts text, tables, images, and diagrams from a PDF, image, or text document."""

    storage_root: Path | None
    document_id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID | None = None
    max_pages: int = 250
    _asset_records: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def _asset_prefix(self) -> str:
        if self.user_id is not None:
            return f"users/{self.user_id}/documents/{self.document_id}/assets"
        return f"users/extracted/{self.document_id}/assets"

    def extract_all_pages(
        self,
        file_path: Path,
        source_type: str = "pdf",
        *,
        on_page_done: Callable[[int, int], None] | None = None,
    ) -> list[ExtractedPage]:
        """Extract all pages from a PDF, image, or plain text file."""
        if source_type == "plain_text":
            return self._extract_plain_text(file_path)
        if source_type == "image":
            return self._extract_image_file(file_path)
        return self._extract_pdf(file_path, on_page_done=on_page_done)

    def _extract_plain_text(self, file_path: Path) -> list[ExtractedPage]:
        """Treat a plain text file as a single page."""
        content = file_path.read_text(encoding="utf-8", errors="replace")
        blocks = [p.strip() for p in content.split("\n\n") if p.strip()] or [content]
        joined = "\n\n".join(blocks).strip()
        raw_chars = len(joined)
        return [
            ExtractedPage(
                page_number=1,
                text_blocks=blocks,
                tables_data=[],
                image_storage_keys=[],
                diagram_storage_keys=[],
                asset_records=[],
                raw_char_count=raw_chars,
                image_count=0,
                table_count=0,
                needs_ocr=raw_chars == 0,
                warning="Plain text document is empty" if raw_chars == 0 else None,
                extraction_method="plain_text",
                confidence=1.0 if raw_chars > 0 else 0.0,
            )
        ]

    def _extract_image_file(self, file_path: Path) -> list[ExtractedPage]:
        """Register an uploaded image as a single page requiring OCR/vision extraction."""
        img_bytes = file_path.read_bytes()
        width = 0
        height = 0
        ext = file_path.suffix.lstrip(".").lower() or "png"
        mime_type = "image/png"
        try:
            with Image.open(io.BytesIO(img_bytes)) as img:
                width, height = img.size
                fmt = (img.format or "PNG").upper()
                if fmt == "JPEG":
                    ext = "jpg"
                    mime_type = "image/jpeg"
                else:
                    ext = "png"
                    mime_type = "image/png"
        except Exception:
            logger.warning("Failed inspecting uploaded image dimensions: %s", file_path.name)

        asset_records: list[dict[str, Any]] = []
        image_keys: list[str] = []
        if self.storage_root is not None:
            asset_id = uuid.uuid4()
            key = f"{self._asset_prefix()}/images/p1_{asset_id}.{ext}"
            dest = (self.storage_root / key).resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(img_bytes)
            image_keys.append(key)
            asset_records.append(
                {
                    "id": asset_id,
                    "document_id": self.document_id,
                    "page_number": 1,
                    "asset_type": "embedded_image",
                    "storage_key": key,
                    "mime_type": mime_type,
                    "width": width,
                    "height": height,
                    "bbox_json": None,
                }
            )
        return [
            ExtractedPage(
                page_number=1,
                text_blocks=[],
                tables_data=[],
                image_storage_keys=image_keys,
                diagram_storage_keys=[],
                asset_records=asset_records,
                raw_char_count=0,
                image_count=1,
                table_count=0,
                needs_ocr=True,
                warning="Image document requires OCR or vision extraction",
                extraction_method="image",
                confidence=0.0,
                page_render_bytes=img_bytes,
            )
        ]

    def _extract_pdf(
        self,
        file_path: Path,
        *,
        on_page_done: Callable[[int, int], None] | None = None,
    ) -> list[ExtractedPage]:
        """Extract all pages from a PDF file using an in-memory byte stream."""
        pdf_bytes = file_path.read_bytes()
        return self.extract_pdf_bytes(pdf_bytes, on_page_done=on_page_done)

    def extract_pdf_bytes(
        self,
        pdf_bytes: bytes,
        *,
        on_page_done: Callable[[int, int], None] | None = None,
    ) -> list[ExtractedPage]:
        """Extract all pages directly from PDF bytes."""
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception:
            logger.exception("Failed to open PDF bytes for extraction")
            return []

        pages: list[ExtractedPage] = []
        table_candidate_indices: set[int] = set()
        try:
            total_pages = min(doc.page_count, self.max_pages)
            for page_idx in range(total_pages):
                page: pymupdf.Page | None = None
                try:
                    page = doc.load_page(page_idx)
                    if page.get_drawings():
                        table_candidate_indices.add(page_idx)
                    extracted = self._extract_page(
                        doc, page, page_idx + 1, strip_headers_footers=total_pages > 1
                    )
                    pages.append(extracted)
                except Exception:
                    logger.exception("Failed to extract page %d", page_idx + 1)
                    pages.append(
                        ExtractedPage(
                            page_number=page_idx + 1,
                            text_blocks=[],
                            tables_data=[],
                            image_storage_keys=[],
                            diagram_storage_keys=[],
                            asset_records=[],
                            raw_char_count=0,
                            image_count=0,
                            table_count=0,
                            needs_ocr=True,
                            warning=f"Page {page_idx + 1}: extraction failed; OCR required",
                        )
                    )
                finally:
                    if page is not None:
                        del page
                if on_page_done is not None:
                    on_page_done(page_idx + 1, total_pages)
        finally:
            doc.close()

        # Optionally supplement with pdfplumber only on pages that have vector lines/tables
        if table_candidate_indices:
            try:
                pages = self._enrich_with_pdfplumber(
                    pdf_bytes, pages, candidate_indices=table_candidate_indices
                )
            except Exception:
                logger.warning("pdfplumber table enrichment failed; proceeding without it")

        return pages

    def _extract_page(
        self,
        doc: pymupdf.Document,
        page: pymupdf.Page,
        page_number: int,
        *,
        strip_headers_footers: bool = False,
    ) -> ExtractedPage:
        page_rect = page.rect
        page_height = page_rect.height

        # --- Text extraction with multi-column clustering ---
        text_blocks = self._extract_text_blocks(
            page, page_height, strip_headers_footers=strip_headers_footers
        )
        joined_text = "\n\n".join(text_blocks).strip()
        raw_char_count = len(joined_text)

        # --- Raster image extraction ---
        image_keys, image_records, image_count = self._extract_images(doc, page, page_number)

        # --- Vector drawing / diagram detection ---
        diagram_keys, diagram_records = self._detect_and_crop_diagrams(page, page_number)

        # --- Scan / garbled text detection ---
        needs_ocr, warning = self._detect_ocr_needed(
            page, page_rect, raw_char_count, image_count
        )

        # Render full page as PNG for OCR if needed
        page_render = None
        if needs_ocr:
            try:
                mat = pymupdf.Matrix(OCR_RENDER_DPI / 72, OCR_RENDER_DPI / 72)
                clip = page.get_pixmap(matrix=mat, colorspace=pymupdf.csRGB)
                page_render = clip.tobytes("png")
            except Exception:
                logger.warning("Failed to render page %d for OCR", page_number)

        all_asset_records = image_records + diagram_records

        return ExtractedPage(
            page_number=page_number,
            text_blocks=text_blocks,
            tables_data=[],
            image_storage_keys=image_keys,
            diagram_storage_keys=diagram_keys,
            asset_records=all_asset_records,
            raw_char_count=raw_char_count,
            image_count=image_count,
            table_count=0,
            needs_ocr=needs_ocr,
            warning=warning,
            extraction_method="pymupdf",
            confidence=0.0 if needs_ocr else 1.0,
            page_render_bytes=page_render,
        )

    def _extract_text_blocks(
        self,
        page: pymupdf.Page,
        page_height: float,
        *,
        strip_headers_footers: bool = False,
    ) -> list[str]:
        """Extract text blocks with multi-column ordering by bounding box x-position."""
        header_y_min = page_height * HEADER_FOOTER_Y_PERCENT
        footer_y_max = page_height * (1.0 - HEADER_FOOTER_Y_PERCENT)

        try:
            raw_blocks = page.get_text("dict", sort=False)["blocks"]
        except Exception:
            return []

        text_blocks_with_bbox: list[tuple[float, float, float, float, str]] = []
        for block in raw_blocks:
            if block.get("type") != 0:
                continue
            x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
            lines_text = []
            for line in block.get("lines", []):
                spans_text = " ".join(
                    span.get("text", "") for span in line.get("spans", [])
                ).strip()
                if spans_text:
                    lines_text.append(spans_text)
            block_text = "\n".join(lines_text).strip()
            if not block_text:
                continue
            # Only trim very short single-line margin headers/footers in multi-page PDFs
            if (
                strip_headers_footers
                and len(block_text) <= 80
                and (y1 < header_y_min or y0 > footer_y_max)
            ):
                continue
            text_blocks_with_bbox.append((x0, y0, x1, y1, block_text))

        if not text_blocks_with_bbox:
            return []

        page_width = page.rect.width
        mid_x = page_width / 2

        left_col: list[tuple[float, float, str]] = []
        right_col: list[tuple[float, float, str]] = []

        for x0, y0, x1, _y1, text in text_blocks_with_bbox:
            x_center = (x0 + x1) / 2
            # Wide blocks spanning across center are treated as single-column/full-width
            if x0 < mid_x * 0.6 and x1 > mid_x * 1.4:
                all_sorted = sorted(text_blocks_with_bbox, key=lambda b: (b[1], b[0]))
                return [b[4] for b in all_sorted]
            if x_center < mid_x:
                left_col.append((y0, x0, text))
            else:
                right_col.append((y0, x0, text))

        left_col.sort(key=lambda b: (b[0], b[1]))
        right_col.sort(key=lambda b: (b[0], b[1]))

        if not left_col or not right_col:
            all_sorted = sorted(text_blocks_with_bbox, key=lambda b: (b[1], b[0]))
            return [b[4] for b in all_sorted]

        return [b[2] for b in left_col] + [b[2] for b in right_col]

    def _extract_images(
        self,
        doc: pymupdf.Document,
        page: pymupdf.Page,
        page_number: int,
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        """Extract embedded raster images and save to private storage."""
        storage_keys: list[str] = []
        records: list[dict[str, Any]] = []
        image_count = 0
        try:
            image_list = page.get_images(full=True)
        except Exception:
            return [], [], 0

        for img_info in image_list:
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                img_bytes = base_image.get("image", b"")
                img_ext = base_image.get("ext", "png").lower()
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)

                if not img_bytes or width < 20 or height < 20:
                    continue

                image_count += 1
                if self.storage_root is None:
                    continue

                mime_type = "image/png" if img_ext == "png" else "image/jpeg"
                asset_id = uuid.uuid4()
                key = f"{self._asset_prefix()}/images/p{page_number}_{asset_id}.{img_ext}"
                dest = (self.storage_root / key).resolve()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(img_bytes)

                storage_keys.append(key)
                records.append(
                    {
                        "id": asset_id,
                        "document_id": self.document_id,
                        "page_number": page_number,
                        "asset_type": "embedded_image",
                        "storage_key": key,
                        "mime_type": mime_type,
                        "width": width,
                        "height": height,
                        "bbox_json": None,
                    }
                )
            except Exception:
                logger.debug("Failed to extract image xref %d on page %d", xref, page_number)

        return storage_keys, records, image_count

    def _detect_and_crop_diagrams(
        self,
        page: pymupdf.Page,
        page_number: int,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Detect vector drawing clusters and render them as cropped PNG assets."""
        if self.storage_root is None:
            return [], []
        storage_keys: list[str] = []
        records: list[dict[str, Any]] = []

        try:
            drawings = page.get_drawings()
        except Exception:
            return [], []

        if not drawings:
            return [], []

        bboxes = [d.get("rect") for d in drawings if d.get("rect")]
        if not bboxes:
            return [], []

        clusters = _cluster_bboxes(bboxes, gap_threshold=20.0)
        page_w = page.rect.width
        page_h = page.rect.height
        rendered_count = 0

        for cluster_bbox in clusters:
            if rendered_count >= 6:
                break
            x0, y0, x1, y1 = cluster_bbox
            w = x1 - x0
            h = y1 - y0
            if w * h < DIAGRAM_MIN_AREA_PX:
                continue
            if page_w > 0 and page_h > 0 and w > page_w * 0.85 and h > page_h * 0.85:
                continue

            try:
                clip = pymupdf.Rect(x0, y0, x1, y1)
                mat = pymupdf.Matrix(1.5, 1.5)
                pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=pymupdf.csRGB)
                diagram_bytes = pix.tobytes("png")
                width = pix.width
                height = pix.height
                rendered_count += 1

                asset_id = uuid.uuid4()
                key = f"{self._asset_prefix()}/diagrams/p{page_number}_{asset_id}.png"
                dest = (self.storage_root / key).resolve()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(diagram_bytes)

                storage_keys.append(key)
                records.append(
                    {
                        "id": asset_id,
                        "document_id": self.document_id,
                        "page_number": page_number,
                        "asset_type": "cropped_diagram",
                        "storage_key": key,
                        "mime_type": "image/png",
                        "width": width,
                        "height": height,
                        "bbox_json": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                    }
                )
            except Exception:
                logger.debug("Failed to render diagram cluster on page %d", page_number)

        return storage_keys, records

    def _detect_ocr_needed(
        self,
        page: pymupdf.Page,
        page_rect: pymupdf.Rect,
        raw_char_count: int,
        image_count: int,
    ) -> tuple[bool, str | None]:
        """Delegate scan/garbled classification using page image coverage and raw text."""
        image_area_ratio = 0.0
        try:
            page_area = page_rect.width * page_rect.height
            if page_area > 0:
                img_area = sum(
                    abs((r.x1 - r.x0) * (r.y1 - r.y0))
                    for r in [
                        pymupdf.Rect(*img.get("bbox", (0, 0, 0, 0)))
                        for img in page.get_image_info()
                    ]
                    if hasattr(r, "x0")
                )
                image_area_ratio = img_area / page_area
        except Exception:
            image_area_ratio = 0.0

        try:
            full_text = page.get_text("text") or ""
        except Exception:
            full_text = ""

        return classify_page(
            raw_char_count=raw_char_count,
            image_count=image_count,
            image_area_ratio=image_area_ratio,
            text=full_text,
        )

    def _enrich_with_pdfplumber(
        self,
        pdf_bytes: bytes,
        pages: list[ExtractedPage],
        *,
        candidate_indices: set[int] | None = None,
    ) -> list[ExtractedPage]:
        """Supplement with pdfplumber table extraction where available."""
        try:
            import pdfplumber  # noqa: PLC0415
        except ImportError:
            logger.debug("pdfplumber not installed; skipping table extraction")
            return pages

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as plumber_pdf:
                for page_result in pages:
                    idx = page_result.page_number - 1
                    if candidate_indices is not None and idx not in candidate_indices:
                        continue
                    if idx >= len(plumber_pdf.pages):
                        continue
                    try:
                        plumber_page = plumber_pdf.pages[idx]
                        raw_tables = plumber_page.extract_tables() or []
                        if raw_tables:
                            page_result.tables_data = raw_tables
                            page_result.table_count = len(raw_tables)
                        plumber_page.flush_cache()
                    except Exception:
                        logger.debug("pdfplumber failed on page %d", page_result.page_number)
        except Exception:
            logger.warning("pdfplumber could not open PDF bytes")

        return pages


def _cluster_bboxes(
    bboxes: list[Any], gap_threshold: float = 20.0
) -> list[tuple[float, float, float, float]]:
    """Merge overlapping or nearby bounding boxes into cluster regions."""
    if not bboxes:
        return []

    def to_tuple(r: Any) -> tuple[float, float, float, float]:
        if hasattr(r, "x0"):
            return (r.x0, r.y0, r.x1, r.y1)
        return tuple(r)[:4]  # type: ignore[return-value]

    regions = [list(to_tuple(b)) for b in bboxes]
    merged = True
    while merged:
        merged = False
        new_regions: list[list[float]] = []
        used = [False] * len(regions)
        for i, r1 in enumerate(regions):
            if used[i]:
                continue
            for j in range(i + 1, len(regions)):
                if used[j]:
                    continue
                r2 = regions[j]
                if (
                    r1[2] + gap_threshold >= r2[0]
                    and r2[2] + gap_threshold >= r1[0]
                    and r1[3] + gap_threshold >= r2[1]
                    and r2[3] + gap_threshold >= r1[1]
                ):
                    r1 = [
                        min(r1[0], r2[0]),
                        min(r1[1], r2[1]),
                        max(r1[2], r2[2]),
                        max(r1[3], r2[3]),
                    ]
                    used[j] = True
                    merged = True
            new_regions.append(r1)
        regions = new_regions

    return [(r[0], r[1], r[2], r[3]) for r in regions]


def extract_pages(
    source: Path | bytes | io.BytesIO,
    *,
    max_pages: int = 250,
) -> list[ExtractedPage]:
    """Convenience helper to extract PDF pages from a Path, bytes, or BytesIO stream."""
    extractor = PDFExtractor(storage_root=None, max_pages=max_pages)
    if isinstance(source, Path):
        return extractor.extract_all_pages(source, source_type="pdf")
    raw_bytes = source if isinstance(source, bytes) else source.getvalue()
    return extractor.extract_pdf_bytes(raw_bytes)
