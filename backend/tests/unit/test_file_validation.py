from __future__ import annotations

import io
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from app.services.document_ingestion.storage import LocalPrivateStorage
from app.services.document_ingestion.validator import (
    FileTooLargeError,
    FileValidationError,
    normalize_mime_type,
    sanitize_filename,
    validate_file_path,
)


def _make_pdf_bytes(page_count: int = 1, *, password: str | None = None) -> bytes:
    doc = pymupdf.open()
    try:
        for i in range(page_count):
            page = doc.new_page()
            page.insert_text((72, 72), f"Sample SSC CHSL Page {i + 1}")
        if password:
            return doc.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                user_pw=password,
                owner_pw=f"{password}_owner",
            )
        return doc.tobytes()
    finally:
        doc.close()


def _make_image_bytes(fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (32, 32), color=(40, 90, 160))
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_sanitize_filename_strips_paths_and_rejects_empty() -> None:
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename(r"C:\Users\student\notes.pdf") == "notes.pdf"

    with pytest.raises(FileValidationError) as empty_exc:
        sanitize_filename("")
    assert empty_exc.value.code == "MISSING_FILENAME"

    with pytest.raises(FileValidationError) as dot_exc:
        sanitize_filename("..")
    assert dot_exc.value.code == "INVALID_FILENAME"


def test_normalize_mime_type() -> None:
    assert normalize_mime_type("Application/PDF; charset=utf-8") == "application/pdf"
    assert normalize_mime_type("image/jpg") == "image/jpeg"
    assert normalize_mime_type(None) is None


def test_validate_valid_pdf_and_images(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(_make_pdf_bytes(page_count=3))
    pdf_meta = validate_file_path(
        pdf_path,
        original_filename="sample.pdf",
        declared_mime_type="application/pdf",
        max_upload_mb=10,
        max_pdf_pages=20,
    )
    assert pdf_meta.source_type == "pdf"
    assert pdf_meta.mime_type == "application/pdf"
    assert pdf_meta.page_count == 3
    assert len(pdf_meta.sha256) == 64

    png_path = tmp_path / "diagram.png"
    png_path.write_bytes(_make_image_bytes("PNG"))
    png_meta = validate_file_path(
        png_path,
        original_filename="diagram.png",
        declared_mime_type="image/png",
        max_upload_mb=10,
        max_pdf_pages=20,
    )
    assert png_meta.source_type == "image"
    assert png_meta.page_count == 1

    jpg_path = tmp_path / "scan.jpg"
    jpg_path.write_bytes(_make_image_bytes("JPEG"))
    jpg_meta = validate_file_path(
        jpg_path,
        original_filename="scan.jpg",
        declared_mime_type="image/jpg",
        max_upload_mb=10,
        max_pdf_pages=20,
    )
    assert jpg_meta.source_type == "image"
    assert jpg_meta.mime_type == "image/jpeg"
    assert jpg_meta.page_count == 1


def test_validate_rejects_unsupported_mime_and_signature_spoofing(tmp_path: Path) -> None:
    txt_path = tmp_path / "notes.txt"
    txt_path.write_bytes(b"hello")
    with pytest.raises(FileValidationError) as ext_exc:
        validate_file_path(
            txt_path,
            original_filename="notes.txt",
            declared_mime_type="text/plain",
            max_upload_mb=10,
            max_pdf_pages=20,
        )
    assert ext_exc.value.code == "UNSUPPORTED_FILE_TYPE"

    spoof_pdf = tmp_path / "fake.pdf"
    spoof_pdf.write_bytes(b"MZ\x90\x00not-a-pdf")
    with pytest.raises(FileValidationError) as mime_exc:
        validate_file_path(
            spoof_pdf,
            original_filename="fake.pdf",
            declared_mime_type="image/png",
            max_upload_mb=10,
            max_pdf_pages=20,
        )
    assert mime_exc.value.code == "MIME_MISMATCH"

    with pytest.raises(FileValidationError) as sig_exc:
        validate_file_path(
            spoof_pdf,
            original_filename="fake.pdf",
            declared_mime_type="application/pdf",
            max_upload_mb=10,
            max_pdf_pages=20,
        )
    assert sig_exc.value.code == "SIGNATURE_MISMATCH"


def test_validate_rejects_empty_oversized_corrupt_encrypted_and_page_limit(tmp_path: Path) -> None:
    empty_path = tmp_path / "empty.pdf"
    empty_path.write_bytes(b"")
    with pytest.raises(FileValidationError) as empty_exc:
        validate_file_path(
            empty_path,
            original_filename="empty.pdf",
            declared_mime_type="application/pdf",
            max_upload_mb=10,
            max_pdf_pages=20,
        )
    assert empty_exc.value.code == "EMPTY_FILE"

    big_path = tmp_path / "big.pdf"
    big_path.write_bytes(b"%PDF-1.4\n" + (b"0" * (1024 * 1024 + 16)))
    with pytest.raises(FileTooLargeError):
        validate_file_path(
            big_path,
            original_filename="big.pdf",
            declared_mime_type="application/pdf",
            max_upload_mb=1,
            max_pdf_pages=20,
        )

    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\nthis-is-corrupt-binary")
    with pytest.raises(FileValidationError) as corrupt_exc:
        validate_file_path(
            corrupt_pdf,
            original_filename="corrupt.pdf",
            declared_mime_type="application/pdf",
            max_upload_mb=10,
            max_pdf_pages=20,
        )
    assert corrupt_exc.value.code == "CORRUPT_PDF"

    encrypted_pdf = tmp_path / "locked.pdf"
    encrypted_pdf.write_bytes(_make_pdf_bytes(page_count=1, password="secret"))
    with pytest.raises(FileValidationError) as enc_exc:
        validate_file_path(
            encrypted_pdf,
            original_filename="locked.pdf",
            declared_mime_type="application/pdf",
            max_upload_mb=10,
            max_pdf_pages=20,
        )
    assert enc_exc.value.code == "ENCRYPTED_PDF"

    too_many_pages = tmp_path / "long.pdf"
    too_many_pages.write_bytes(_make_pdf_bytes(page_count=4))
    with pytest.raises(FileValidationError) as pages_exc:
        validate_file_path(
            too_many_pages,
            original_filename="long.pdf",
            declared_mime_type="application/pdf",
            max_upload_mb=10,
            max_pdf_pages=2,
        )
    assert pages_exc.value.code == "PAGE_LIMIT_EXCEEDED"

    corrupt_png = tmp_path / "broken.png"
    corrupt_png.write_bytes(b"\x89PNG\r\n\x1a\nbroken-image-bytes")
    with pytest.raises(FileValidationError) as img_exc:
        validate_file_path(
            corrupt_png,
            original_filename="broken.png",
            declared_mime_type="image/png",
            max_upload_mb=10,
            max_pdf_pages=20,
        )
    assert img_exc.value.code == "CORRUPT_IMAGE"


def test_local_private_storage_crud_and_traversal_guard(tmp_path: Path) -> None:
    storage = LocalPrivateStorage(tmp_path / "private_storage")
    key = "users/u1/documents/d1/file.pdf"
    storage.save_bytes(key, b"%PDF-1.4 sample")
    assert storage.exists(key) is True
    with storage.open_read(key) as fh:
        assert fh.read() == b"%PDF-1.4 sample"

    with pytest.raises(ValueError):
        storage.save_bytes("../escape.pdf", b"bad")
    with pytest.raises(ValueError):
        storage.exists("users/../../escape.pdf")

    assert storage.delete_prefix("users/u1/documents/d1") is True
    assert storage.exists(key) is False
