"""PDF fixture factory for M2 extraction tests.

Produces deterministic synthetic PDFs without any third-party test-data files.
Requires only `pymupdf` (already a project dependency).
"""
from __future__ import annotations

import struct
import zlib

# ---------------------------------------------------------------------------
# Minimal raw-PDF builder (no pymupdf needed to BUILD; pymupdf used to verify)
# ---------------------------------------------------------------------------


def _xref_offset(body: bytes, obj_offsets: list[int], n_objs: int) -> bytes:
    """Return the xref table + trailer for a minimal PDF."""
    xref = b"xref\r\n"
    xref += f"0 {n_objs + 1}\r\n".encode()
    xref += b"0000000000 65535 f \r\n"
    for off in obj_offsets:
        xref += f"{off:010d} 00000 n \r\n".encode()
    return xref


def build_text_pdf(pages: list[str]) -> bytes:
    """Return a minimal valid PDF with one text layer per page.

    Args:
        pages: List of plain-text strings, one per page.
    """
    objects: list[bytes] = []
    obj_offsets: list[int] = []
    body = b"%PDF-1.4\n"

    def add_obj(content: bytes) -> int:
        obj_id = len(objects) + 1
        obj_offsets.append(len(body) + sum(len(o) for o in objects))
        # We'll compute actual offsets below; use placeholder accumulator
        objects.append(content)
        return obj_id

    # Build page content streams first so we know object IDs
    # Layout: obj 1 = catalog, obj 2 = pages, obj 3..n+2 = page objs,
    # obj n+3..2n+2 = content streams
    n = len(pages)
    catalog_id = 1
    pages_id = 2
    page_ids = list(range(3, 3 + n))
    content_ids = list(range(3 + n, 3 + 2 * n))

    all_objs: list[tuple[int, bytes]] = []  # (obj_id, raw_obj_bytes)

    # Content stream objects
    for i, text in enumerate(pages):
        safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_data = (
            f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET\n"
        ).encode("latin-1", errors="replace")
        stream_obj = (
            f"{content_ids[i]} 0 obj\n"
            f"<< /Length {len(stream_data)} >>\n"
            f"stream\n"
        ).encode() + stream_data + b"\nendstream\nendobj\n"
        all_objs.append((content_ids[i], stream_obj))

    # Page objects
    for i in range(n):
        page_obj = (
            f"{page_ids[i]} 0 obj\n"
            f"<< /Type /Page /Parent {pages_id} 0 R"
            f" /MediaBox [0 0 612 792]"
            f" /Contents {content_ids[i]} 0 R"
            f" /Resources << /Font << /F1 << /Type /Font /Subtype /Type1"
            f" /BaseFont /Helvetica >> >> >> >>\n"
            f"endobj\n"
        ).encode()
        all_objs.append((page_ids[i], page_obj))

    # Pages dict
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_obj = (
        f"{pages_id} 0 obj\n"
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>\n"
        f"endobj\n"
    ).encode()
    all_objs.append((pages_id, pages_obj))

    # Catalog
    catalog_obj = (
        f"{catalog_id} 0 obj\n"
        f"<< /Type /Catalog /Pages {pages_id} 0 R >>\n"
        f"endobj\n"
    ).encode()
    all_objs.append((catalog_id, catalog_obj))

    # Sort by object ID and assemble body
    all_objs.sort(key=lambda x: x[0])
    id_to_offset: dict[int, int] = {}
    buf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    for obj_id, obj_bytes in all_objs:
        id_to_offset[obj_id] = len(buf)
        buf += obj_bytes

    # xref
    xref_offset = len(buf)
    total_objs = max(oid for oid, _ in all_objs)
    xref = f"xref\n0 {total_objs + 1}\n0000000000 65535 f \n".encode()
    for oid in range(1, total_objs + 1):
        off = id_to_offset.get(oid, 0)
        xref += f"{off:010d} 00000 n \n".encode()

    trailer = (
        f"trailer\n<< /Size {total_objs + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    return buf + xref + trailer


def build_image_only_pdf(n_pages: int = 2) -> bytes:
    """Return a PDF where every page contains only a raster image (no text layer).

    Uses a tiny 1×1 white PNG embedded as an XObject so PyMuPDF extracts
    zero selectable characters but reports `image_count >= 1`.
    """
    # Minimal 1×1 white PNG
    def _make_png() -> bytes:
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

        raw = b"\x00\xff\xff\xff"  # filter byte + 1 white RGB pixel
        compressed = zlib.compress(raw)
        idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
        idat = (
            struct.pack(">I", len(compressed))
            + b"IDAT"
            + compressed
            + struct.pack(">I", idat_crc)
        )

        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        return sig + ihdr + idat + iend

    png_bytes = _make_png()

    # Assign object IDs
    # 1=catalog, 2=pages, 3..n+2=pages, n+3..2n+2=content streams,
    # 2n+3=image XObject (shared)
    n = n_pages
    catalog_id = 1
    pages_id = 2
    page_ids = list(range(3, 3 + n))
    content_ids = list(range(3 + n, 3 + 2 * n))
    image_id = 3 + 2 * n

    all_objs: list[tuple[int, bytes]] = []
    id_to_offset: dict[int, int] = {}

    # Image XObject
    img_obj = (
        f"{image_id} 0 obj\n"
        f"<< /Type /XObject /Subtype /Image /Width 1 /Height 1"
        f" /ColorSpace /DeviceRGB /BitsPerComponent 8"
        f" /Filter /FlateDecode /Length {len(png_bytes)} >>\n"
        f"stream\n"
    ).encode() + png_bytes + b"\nendstream\nendobj\n"
    all_objs.append((image_id, img_obj))

    # Content streams — just paint the image XObject
    for i in range(n):
        stream_data = b"q 100 0 0 100 50 650 cm /Im1 Do Q\n"
        cs_obj = (
            f"{content_ids[i]} 0 obj\n"
            f"<< /Length {len(stream_data)} >>\n"
            f"stream\n"
        ).encode() + stream_data + b"\nendstream\nendobj\n"
        all_objs.append((content_ids[i], cs_obj))

    # Page objects
    for i in range(n):
        page_obj = (
            f"{page_ids[i]} 0 obj\n"
            f"<< /Type /Page /Parent {pages_id} 0 R"
            f" /MediaBox [0 0 612 792]"
            f" /Contents {content_ids[i]} 0 R"
            f" /Resources << /XObject << /Im1 {image_id} 0 R >> >> >>\n"
            f"endobj\n"
        ).encode()
        all_objs.append((page_ids[i], page_obj))

    # Pages dict
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_obj = (
        f"{pages_id} 0 obj\n"
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>\n"
        f"endobj\n"
    ).encode()
    all_objs.append((pages_id, pages_obj))

    # Catalog
    cat_obj = (
        f"{catalog_id} 0 obj\n"
        f"<< /Type /Catalog /Pages {pages_id} 0 R >>\n"
        f"endobj\n"
    ).encode()
    all_objs.append((catalog_id, cat_obj))

    # Assemble
    all_objs.sort(key=lambda x: x[0])
    buf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    for obj_id, obj_bytes in all_objs:
        id_to_offset[obj_id] = len(buf)
        buf += obj_bytes

    xref_offset = len(buf)
    total_objs = max(oid for oid, _ in all_objs)
    xref = f"xref\n0 {total_objs + 1}\n0000000000 65535 f \n".encode()
    for oid in range(1, total_objs + 1):
        off = id_to_offset.get(oid, 0)
        xref += f"{off:010d} 00000 n \n".encode()

    trailer = (
        f"trailer\n<< /Size {total_objs + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return buf + xref + trailer


def build_mcq_pdf(stem: str, options: list[str]) -> bytes:
    """Return a 1-page PDF whose text simulates a classic SSC MCQ question.

    The stem and options must NOT be split across pages (chunker invariant).
    """
    lines = [stem] + [f"({chr(65 + i)}) {opt}" for i, opt in enumerate(options)]
    full_text = "  ".join(lines)
    return build_text_pdf([full_text])


def build_passage_mcq_pdf(passage: str, questions: list[str]) -> bytes:
    """Return a 1-page PDF with a reading passage followed by MCQs.

    The passage + all dependent questions must NOT be split (chunker invariant).
    """
    full_text = passage + "  " + "  ".join(questions)
    return build_text_pdf([full_text])
