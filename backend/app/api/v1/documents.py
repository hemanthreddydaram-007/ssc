from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.repositories.document_repo import DocumentRepository
from app.repositories.job_repo import AssetNotFoundError, JobService
from app.schemas.document import (
    DeleteDocumentResponse,
    DocumentListResponse,
    DocumentOut,
    DocumentUpdateRequest,
    TextIngestionRequest,
)
from app.schemas.job import (
    CoverageAuditOut,
    DocumentPagesResponse,
    ProcessDocumentRequest,
    ProcessingJobOut,
)
from app.services.document_ingestion import (
    DocumentAccessDeniedError,
    DocumentIngestionService,
    DocumentNotFoundError,
    DuplicateDocumentError,
    FileTooLargeError,
    FileValidationError,
    InvalidReferenceError,
    LocalPrivateStorage,
)
from app.services.extraction.extraction_pipeline import run_extraction_job_in_session

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

_UPLOAD_CHUNK_BYTES = 1024 * 1024


def get_ingestion_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentIngestionService:
    """Build the document ingestion service with repository and private storage."""
    repo = DocumentRepository(db)
    storage = LocalPrivateStorage(settings.storage_root)
    return DocumentIngestionService(repo=repo, storage=storage, settings=settings)


def _parse_optional_uuid(raw_value: str | None) -> UUID | None:
    if raw_value is None:
        return None
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    try:
        return UUID(cleaned)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid exam_config_id UUID",
        ) from exc


def _duplicate_conflict_response(exc: DuplicateDocumentError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Duplicate document detected",
            "code": "DUPLICATE_DOCUMENT",
            "existing_document_id": str(exc.existing_document_id),
        },
    )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    exam_config_id: str | None = Form(default=None),
    subject_code: str | None = Form(default=None),
    chapter_or_topic_hint: str | None = Form(default=None),
    material_type: str = Form(default="other"),
    language: str = Form(default="en"),
    source_label: str | None = Form(default=None),
    allow_duplicate: bool = Form(default=False),
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    service: DocumentIngestionService = Depends(get_ingestion_service),
) -> DocumentOut | JSONResponse:
    """Upload a PDF or image file with signature, size, page-count, and duplicate checks."""
    parsed_exam_config_id = _parse_optional_uuid(exam_config_id)
    max_bytes = settings.max_upload_mb * 1024 * 1024

    tmp_dir = settings.storage_root / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(dir=tmp_dir, delete=False) as tmp_file:
            temp_path = Path(tmp_file.name)
            hasher = hashlib.sha256()
            total_bytes = 0
            while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise FileTooLargeError(settings.max_upload_mb)
                hasher.update(chunk)
                tmp_file.write(chunk)
        await file.close()

        return service.ingest_file(
            user_id=current_user.id,
            temp_path=temp_path,
            original_filename=file.filename,
            declared_mime_type=file.content_type,
            sha256_digest=hasher.hexdigest(),
            title=title,
            exam_config_id=parsed_exam_config_id,
            subject_code=subject_code,
            chapter_or_topic_hint=chapter_or_topic_hint,
            material_type=material_type,
            language=language,
            source_label=source_label,
            allow_duplicate=allow_duplicate,
        )
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=exc.detail,
        ) from exc
    except (FileValidationError, InvalidReferenceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except DuplicateDocumentError as exc:
        return _duplicate_conflict_response(exc)
    finally:
        await file.close()
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temporary upload file %s", temp_path)


@router.post("/text", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def ingest_plain_text(
    payload: TextIngestionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: DocumentIngestionService = Depends(get_ingestion_service),
) -> DocumentOut | JSONResponse:
    """Ingest pasted plain text as a private study document."""
    try:
        return service.ingest_text(user_id=current_user.id, payload=payload)
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=exc.detail,
        ) from exc
    except (FileValidationError, InvalidReferenceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except DuplicateDocumentError as exc:
        return _duplicate_conflict_response(exc)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    subject_code: str | None = Query(default=None),
    material_type: str | None = Query(default=None),
    doc_status: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: DocumentIngestionService = Depends(get_ingestion_service),
) -> DocumentListResponse:
    """List documents owned by the current user with optional filtering."""
    return service.list_documents(
        user_id=current_user.id,
        subject_code=subject_code,
        material_type=material_type,
        status=doc_status,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: DocumentIngestionService = Depends(get_ingestion_service),
) -> DocumentOut:
    """Return details for a single owned document."""
    try:
        return service.get_document(document_id=document_id, user_id=current_user.id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: UUID,
    payload: DocumentUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: DocumentIngestionService = Depends(get_ingestion_service),
) -> DocumentOut:
    """Update editable metadata on an owned document."""
    try:
        return service.update_document(
            document_id=document_id, user_id=current_user.id, payload=payload
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
def delete_document(
    document_id: UUID,
    cascade_derived: bool = Query(default=True),
    current_user: CurrentUser = Depends(get_current_user),
    service: DocumentIngestionService = Depends(get_ingestion_service),
) -> DeleteDocumentResponse:
    """Delete an owned document and remove its private stored file(s)."""
    try:
        return service.delete_document(
            document_id=document_id,
            user_id=current_user.id,
            cascade_derived=cascade_derived,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    """Build the extraction/job service."""
    return JobService(db)


def _assert_owned_document(
    ingestion_service: DocumentIngestionService,
    *,
    document_id: UUID,
    user_id: UUID,
) -> DocumentOut:
    try:
        return ingestion_service.get_document(document_id=document_id, user_id=user_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/{document_id}/process",
    response_model=ProcessingJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    payload: ProcessDocumentRequest = Body(default_factory=ProcessDocumentRequest),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ingestion_service: DocumentIngestionService = Depends(get_ingestion_service),
    job_service: JobService = Depends(get_job_service),
) -> ProcessingJobOut:
    """Enqueue page-level extraction, OCR fallback, and semantic chunking for a document."""
    doc = _assert_owned_document(
        ingestion_service, document_id=document_id, user_id=current_user.id
    )
    job = job_service.create_extraction_job(
        document_id=document_id,
        user_id=current_user.id,
        job_type=payload.mode,
        document_title=doc.title,
    )
    session_factory = sessionmaker(
        bind=db.get_bind(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    background_tasks.add_task(
        run_extraction_job_in_session,
        session_factory=session_factory,
        storage_root=settings.storage_root,
        document_id=document_id,
        job_id=job.id,
        mode=payload.mode,
        force_reextract=payload.force_reextract,
        page_numbers=payload.page_numbers,
    )
    return job


@router.get("/{document_id}/pages", response_model=DocumentPagesResponse)
def get_document_pages(
    document_id: UUID,
    needs_ocr_only: bool = Query(default=False),
    current_user: CurrentUser = Depends(get_current_user),
    ingestion_service: DocumentIngestionService = Depends(get_ingestion_service),
    job_service: JobService = Depends(get_job_service),
) -> DocumentPagesResponse:
    """Return extracted page-level text, tables, warnings, and asset references."""
    _assert_owned_document(
        ingestion_service, document_id=document_id, user_id=current_user.id
    )
    return job_service.get_pages(document_id, needs_ocr_only=needs_ocr_only)


@router.get("/{document_id}/assets/{asset_id}")
def get_document_asset(
    document_id: UUID,
    asset_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    ingestion_service: DocumentIngestionService = Depends(get_ingestion_service),
    job_service: JobService = Depends(get_job_service),
) -> StreamingResponse:
    """Stream a privately stored diagram or embedded image for an owned document."""
    _assert_owned_document(
        ingestion_service, document_id=document_id, user_id=current_user.id
    )
    try:
        asset = job_service.get_asset(document_id=document_id, asset_id=asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    storage = LocalPrivateStorage(settings.storage_root)
    try:
        if not storage.exists(asset.storage_key):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored asset file not found",
            )
        with storage.open_read(asset.storage_key) as asset_file:
            data = asset_file.read()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Asset unavailable"
        ) from exc

    return StreamingResponse(
        iter([data]),
        media_type=asset.mime_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/{document_id}/coverage", response_model=CoverageAuditOut)
def get_document_coverage(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    ingestion_service: DocumentIngestionService = Depends(get_ingestion_service),
    job_service: JobService = Depends(get_job_service),
) -> CoverageAuditOut:
    """Return deterministic page, OCR, table, diagram, and record counts."""
    _assert_owned_document(
        ingestion_service, document_id=document_id, user_id=current_user.id
    )
    return job_service.get_coverage_audit(document_id)
