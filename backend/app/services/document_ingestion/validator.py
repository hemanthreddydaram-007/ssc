from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image, UnidentifiedImageError

ALLOWED_SPECS: dict[str, tuple[str, str, bytes]] = {
    ".pdf": ("pdf", "application/pdf", b"%PDF-"),
    ".jpg": ("image", "image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image", "image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image", "image/png", b"\x89PNG\r\n\x1a\n"),
}


class FileValidationError(Exception):
    """Raised when an uploaded file fails format, signature, size, or integrity checks."""

    def __init__(self, detail: str, *, code: str = "INVALID_FILE") -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


class FileTooLargeError(FileValidationError):
    """Raised when an uploaded file or text payload exceeds the configured byte limit."""

    def __init__(self, max_mb: int) -> None:
        super().__init__(
            f"File exceeds maximum allowed size of {max_mb} MB",
            code="FILE_TOO_LARGE",
        )


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    """Metadata produced after validating an uploaded file on disk."""

    original_filename: str
    extension: str
    source_type: str
    mime_type: str
    file_size_bytes: int
    sha256: str
    page_count: int


def sanitize_filename(raw_filename: str | None) -> str:
    """Extract a safe basename for display metadata without allowing path components."""
    if not raw_filename:
        raise FileValidationError("Filename is required", code="MISSING_FILENAME")
    cleaned = Path(raw_filename.replace("\\", "/")).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise FileValidationError("Invalid filename", code="INVALID_FILENAME")
    return cleaned[:255]


def normalize_mime_type(declared_mime: str | None) -> str | None:
    """Normalize a declared MIME type by stripping parameters and lowercasing."""
    if not declared_mime:
        return None
    normalized = declared_mime.split(";", 1)[0].strip().lower()
    if normalized == "image/jpg":
        return "image/jpeg"
    return normalized or None


def compute_sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest of an in-memory payload."""
    return hashlib.sha256(data).hexdigest()


def validate_file_path(
    file_path: Path,
    *,
    original_filename: str | None,
    declared_mime_type: str | None,
    max_upload_mb: int,
    max_pdf_pages: int,
    sha256_digest: str | None = None,
) -> ValidatedUpload:
    """Validate extension, MIME type, magic bytes, size, and PDF/image readability."""
    safe_name = sanitize_filename(original_filename)
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_SPECS:
        raise FileValidationError(
            "Unsupported file type. Accepted formats: PDF, JPG, PNG",
            code="UNSUPPORTED_FILE_TYPE",
        )

    source_type, expected_mime, magic_prefix = ALLOWED_SPECS[ext]
    normalized_mime = normalize_mime_type(declared_mime_type)
    if normalized_mime is not None and normalized_mime != expected_mime:
        raise FileValidationError(
            f"Declared MIME type '{normalized_mime}' does not match '{ext}'",
            code="MIME_MISMATCH",
        )

    if not file_path.exists():
        raise FileValidationError("Uploaded file could not be read", code="MISSING_FILE")

    file_size = file_path.stat().st_size
    if file_size <= 0:
        raise FileValidationError("Uploaded file is empty", code="EMPTY_FILE")

    max_bytes = max_upload_mb * 1024 * 1024
    if file_size > max_bytes:
        raise FileTooLargeError(max_upload_mb)

    with file_path.open("rb") as fh:
        header = fh.read(16)
        if not header.startswith(magic_prefix):
            raise FileValidationError(
                f"File signature does not match expected {ext} format",
                code="SIGNATURE_MISMATCH",
            )
        if sha256_digest is None:
            fh.seek(0)
            hasher = hashlib.sha256()
            while chunk := fh.read(1024 * 1024):
                hasher.update(chunk)
            sha256_digest = hasher.hexdigest()

    if source_type == "pdf":
        page_count = _validate_pdf(file_path, max_pdf_pages=max_pdf_pages)
    else:
        page_count = _validate_image(file_path, expected_extension=ext)

    return ValidatedUpload(
        original_filename=safe_name,
        extension=ext,
        source_type=source_type,
        mime_type=expected_mime,
        file_size_bytes=file_size,
        sha256=sha256_digest,
        page_count=page_count,
    )


def _validate_pdf(file_path: Path, *, max_pdf_pages: int) -> int:
    """Verify PDF structural integrity, encryption status, and page bounds via PyMuPDF."""
    doc: pymupdf.Document | None = None
    try:
        # Read bounded bytes so PyMuPDF never holds a Windows file lock if parsing fails.
        doc = pymupdf.open(stream=file_path.read_bytes(), filetype="pdf")
    except Exception as exc:
        raise FileValidationError(
            "Invalid or corrupt PDF file",
            code="CORRUPT_PDF",
        ) from exc

    try:
        if doc.is_encrypted or doc.needs_pass:
            raise FileValidationError(
                "Encrypted or password-protected PDF files are not supported",
                code="ENCRYPTED_PDF",
            )
        page_count = int(doc.page_count)
        if page_count <= 0:
            raise FileValidationError("PDF contains no pages", code="EMPTY_PDF")
        if page_count > max_pdf_pages:
            raise FileValidationError(
                f"PDF exceeds maximum allowed page count of {max_pdf_pages}",
                code="PAGE_LIMIT_EXCEEDED",
            )
        try:
            doc.load_page(0)
        except Exception as exc:
            raise FileValidationError(
                "PDF first page could not be parsed; file may be corrupt",
                code="CORRUPT_PDF",
            ) from exc
        return page_count
    finally:
        doc.close()


def _validate_image(file_path: Path, *, expected_extension: str) -> int:
    """Verify image integrity and format alignment via Pillow."""
    expected_format = "PNG" if expected_extension == ".png" else "JPEG"
    try:
        with Image.open(file_path) as img:
            img.verify()
        with Image.open(file_path) as img:
            if img.format != expected_format:
                raise FileValidationError(
                    f"Image content format '{img.format}' does not match '{expected_extension}'",
                    code="SIGNATURE_MISMATCH",
                )
            if img.width <= 0 or img.height <= 0:
                raise FileValidationError("Image has invalid dimensions", code="CORRUPT_IMAGE")
    except FileValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise FileValidationError(
            "Invalid or corrupt image file",
            code="CORRUPT_IMAGE",
        ) from exc
    return 1
