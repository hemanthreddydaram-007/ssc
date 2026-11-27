from __future__ import annotations

import re
import uuid
from pathlib import Path
from uuid import UUID

from app.core.config import Settings
from app.models.document import Document
from app.repositories.document_repo import DocumentRepository
from app.schemas.document import (
    DeleteDocumentResponse,
    DocumentListResponse,
    DocumentOut,
    DocumentUpdateRequest,
    TextIngestionRequest,
)
from app.services.document_ingestion.storage import StorageBackend
from app.services.document_ingestion.validator import (
    FileTooLargeError,
    compute_sha256_bytes,
    validate_file_path,
)


class DuplicateDocumentError(Exception):
    """Raised when an active document with the same SHA-256 already exists for the user."""

    def __init__(self, existing_document_id: UUID) -> None:
        super().__init__("Duplicate document detected")
        self.existing_document_id = existing_document_id


class DocumentNotFoundError(Exception):
    """Raised when a document cannot be found."""


class DocumentAccessDeniedError(Exception):
    """Raised when a document belongs to another user."""


class InvalidReferenceError(Exception):
    """Raised when a referenced foreign resource (e.g., exam_config_id) does not exist."""


def _slugify_filename(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", title.strip()).strip("._-")
    if not cleaned:
        cleaned = "pasted_notes"
    return f"{cleaned[:200]}.txt"


class DocumentIngestionService:
    """Coordinates document validation, private storage, metadata updates, and deletion."""

    def __init__(
        self,
        repo: DocumentRepository,
        storage: StorageBackend,
        settings: Settings,
    ) -> None:
        self.repo = repo
        self.storage = storage
        self.settings = settings

    def _validate_exam_config(self, exam_config_id: UUID | None) -> None:
        if exam_config_id is not None and not self.repo.exam_config_exists(exam_config_id):
            raise InvalidReferenceError("Referenced exam_config_id does not exist")

    def _check_duplicate(self, user_id: UUID, sha256: str, allow_duplicate: bool) -> None:
        if allow_duplicate:
            return
        existing = self.repo.find_active_by_sha256(user_id, sha256)
        if existing is not None:
            raise DuplicateDocumentError(existing.id)

    def ingest_file(
        self,
        *,
        user_id: UUID,
        temp_path: Path,
        original_filename: str | None,
        declared_mime_type: str | None,
        sha256_digest: str | None = None,
        title: str | None = None,
        exam_config_id: UUID | None = None,
        subject_code: str | None = None,
        chapter_or_topic_hint: str | None = None,
        material_type: str = "other",
        language: str = "en",
        source_label: str | None = None,
        allow_duplicate: bool = False,
    ) -> DocumentOut:
        """Validate a temporary upload file, store it privately, and create its Document record."""
        validated = validate_file_path(
            temp_path,
            original_filename=original_filename,
            declared_mime_type=declared_mime_type,
            max_upload_mb=self.settings.max_upload_mb,
            max_pdf_pages=self.settings.max_pdf_pages,
            sha256_digest=sha256_digest,
        )
        self._validate_exam_config(exam_config_id)
        self._check_duplicate(user_id, validated.sha256, allow_duplicate)

        doc_id = uuid.uuid4()
        storage_key = f"users/{user_id}/documents/{doc_id}/{uuid.uuid4()}{validated.extension}"
        self.storage.save_from_path(storage_key, temp_path)

        resolved_title = (
            (title or "").strip() or Path(validated.original_filename).stem or "Untitled"
        )
        doc = Document(
            id=doc_id,
            user_id=user_id,
            title=resolved_title[:255],
            original_filename=validated.original_filename,
            source_type=validated.source_type,
            mime_type=validated.mime_type,
            file_size_bytes=validated.file_size_bytes,
            sha256=validated.sha256,
            storage_key=storage_key,
            exam_config_id=exam_config_id,
            subject_code=(subject_code or "").strip() or None,
            chapter_or_topic_hint=(chapter_or_topic_hint or "").strip() or None,
            material_type=(material_type or "other").strip() or "other",
            language=(language or "en").strip() or "en",
            source_label=(source_label or "").strip() or None,
            page_count=validated.page_count,
            status="uploaded",
        )
        try:
            created = self.repo.create(doc)
        except Exception:
            self.storage.delete_prefix(f"users/{user_id}/documents/{doc_id}")
            raise
        return DocumentOut.model_validate(created)

    def ingest_text(self, *, user_id: UUID, payload: TextIngestionRequest) -> DocumentOut:
        """Persist pasted plain text as a private `.txt` document."""
        encoded = payload.content.encode("utf-8")
        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        if len(encoded) > max_bytes:
            raise FileTooLargeError(self.settings.max_upload_mb)

        self._validate_exam_config(payload.exam_config_id)
        sha256 = compute_sha256_bytes(encoded)
        self._check_duplicate(user_id, sha256, payload.allow_duplicate)

        doc_id = uuid.uuid4()
        storage_key = f"users/{user_id}/documents/{doc_id}/{uuid.uuid4()}.txt"
        self.storage.save_bytes(storage_key, encoded)

        doc = Document(
            id=doc_id,
            user_id=user_id,
            title=payload.title,
            original_filename=_slugify_filename(payload.title),
            source_type="plain_text",
            mime_type="text/plain",
            file_size_bytes=len(encoded),
            sha256=sha256,
            storage_key=storage_key,
            exam_config_id=payload.exam_config_id,
            subject_code=payload.subject_code,
            chapter_or_topic_hint=payload.chapter_or_topic_hint,
            material_type=payload.material_type,
            language=payload.language,
            source_label=payload.source_label,
            page_count=1,
            status="uploaded",
        )
        try:
            created = self.repo.create(doc)
        except Exception:
            self.storage.delete_prefix(f"users/{user_id}/documents/{doc_id}")
            raise
        return DocumentOut.model_validate(created)

    def list_documents(
        self,
        *,
        user_id: UUID,
        subject_code: str | None = None,
        material_type: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> DocumentListResponse:
        """List active documents belonging to the user."""
        items, total = self.repo.list_for_user(
            user_id,
            subject_code=subject_code,
            material_type=material_type,
            status=status,
            q=q,
            limit=limit,
            offset=offset,
        )
        return DocumentListResponse(
            items=[DocumentOut.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    def _get_owned_document(self, *, document_id: UUID, user_id: UUID) -> Document:
        doc = self.repo.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError("Document not found")
        if doc.user_id != user_id:
            raise DocumentAccessDeniedError("You do not have access to this document")
        return doc

    def get_document(self, *, document_id: UUID, user_id: UUID) -> DocumentOut:
        """Retrieve a single owned document."""
        doc = self._get_owned_document(document_id=document_id, user_id=user_id)
        return DocumentOut.model_validate(doc)

    def update_document(
        self,
        *,
        document_id: UUID,
        user_id: UUID,
        payload: DocumentUpdateRequest,
    ) -> DocumentOut:
        """Update user-editable metadata fields on an owned document."""
        doc = self._get_owned_document(document_id=document_id, user_id=user_id)
        updates = payload.model_dump(exclude_unset=True)
        if "exam_config_id" in updates:
            self._validate_exam_config(updates["exam_config_id"])
        for field, value in updates.items():
            setattr(doc, field, value)
        saved = self.repo.save(doc)
        return DocumentOut.model_validate(saved)

    def delete_document(
        self,
        *,
        document_id: UUID,
        user_id: UUID,
        cascade_derived: bool = True,
    ) -> DeleteDocumentResponse:
        """Delete an owned document and its private stored files."""
        doc = self._get_owned_document(document_id=document_id, user_id=user_id)
        asset_keys = self.repo.list_asset_storage_keys(doc.id)
        primary_key = doc.storage_key
        doc_prefix = f"users/{doc.user_id}/documents/{doc.id}"

        self.repo.delete_document(doc, cascade_derived=cascade_derived)

        removed = self.storage.delete_prefix(doc_prefix)
        if not removed:
            removed = self.storage.delete(primary_key)
        for key in asset_keys:
            self.storage.delete(key)

        return DeleteDocumentResponse(deleted_id=document_id, storage_removed=removed)
