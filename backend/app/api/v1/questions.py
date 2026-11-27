from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai.provider import AIConfigurationError, AIProviderError, LLMProvider, get_llm_provider
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.question import (
    DeleteQuestionResponse,
    QuestionDetailOut,
    QuestionGenerateRequest,
    QuestionGenerateResponse,
    QuestionImportRequest,
    QuestionImportResponse,
    QuestionListResponse,
    QuestionUpdateRequest,
)
from app.services.question_generation import (
    NoSourceKnowledgeError,
    PYQImportService,
    QuestionAccessDeniedError,
    QuestionDocumentNotFoundError,
    QuestionGenerationFailedError,
    QuestionGenerationService,
    QuestionIngestionService,
    QuestionInvalidReferenceError,
    QuestionNotFoundError,
)

router = APIRouter(tags=["questions"])


def get_question_service(db: Session = Depends(get_db)) -> QuestionIngestionService:
    """Build a QuestionIngestionService bound to the current DB session."""
    return QuestionIngestionService(db)


@router.get("/questions", response_model=QuestionListResponse)
def list_questions(
    document_id: UUID | None = Query(default=None),
    subject_code: str | None = Query(default=None),
    topic_id: UUID | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    validation_status: str | None = Query(default=None),
    pyq_year: int | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: QuestionIngestionService = Depends(get_question_service),
) -> QuestionListResponse:
    """List questions in the user's question bank with optional filters."""
    try:
        return service.list_questions(
            current_user.id,
            document_id=document_id,
            subject_code=subject_code,
            topic_id=topic_id,
            difficulty=difficulty,
            origin=origin,
            validation_status=validation_status,
            pyq_year=pyq_year,
            q=q,
            limit=limit,
            offset=offset,
        )
    except QuestionDocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except QuestionAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/documents/{document_id}/questions", response_model=QuestionListResponse)
def list_document_questions(
    document_id: UUID,
    subject_code: str | None = Query(default=None),
    topic_id: UUID | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    validation_status: str | None = Query(default=None),
    pyq_year: int | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: QuestionIngestionService = Depends(get_question_service),
) -> QuestionListResponse:
    """List extracted and generated questions belonging to an owned document."""
    try:
        return service.list_questions(
            current_user.id,
            document_id=document_id,
            subject_code=subject_code,
            topic_id=topic_id,
            difficulty=difficulty,
            origin=origin,
            validation_status=validation_status,
            pyq_year=pyq_year,
            q=q,
            limit=limit,
            offset=offset,
        )
    except QuestionDocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except QuestionAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/questions/{question_id}", response_model=QuestionDetailOut)
def get_question(
    question_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: QuestionIngestionService = Depends(get_question_service),
) -> QuestionDetailOut:
    """Return full question details, explanation, and provenance (outside active tests)."""
    try:
        return service.get_question(question_id=question_id, user_id=current_user.id)
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except QuestionAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/questions/generate",
    response_model=QuestionGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_questions(
    payload: QuestionGenerateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> QuestionGenerateResponse:
    """Generate and validate MCQs grounded in stored concepts and facts."""
    service = QuestionGenerationService(db, llm_provider)
    try:
        return service.generate(user_id=current_user.id, payload=payload)
    except QuestionDocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except QuestionAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (NoSourceKnowledgeError, QuestionGenerationFailedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AIConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/questions/import",
    response_model=QuestionImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_questions(
    payload: QuestionImportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuestionImportResponse:
    """Import structured JSON or CSV PYQ batches through validation and deduplication."""
    service = PYQImportService(db)
    try:
        return service.import_questions(user_id=current_user.id, payload=payload)
    except QuestionDocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except QuestionAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except QuestionInvalidReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.patch("/questions/{question_id}", response_model=QuestionDetailOut)
def update_question(
    question_id: UUID,
    payload: QuestionUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: QuestionIngestionService = Depends(get_question_service),
) -> QuestionDetailOut:
    """Manually review or edit an owned question in the Question Bank."""
    try:
        return service.update_question(
            question_id=question_id, user_id=current_user.id, payload=payload
        )
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except QuestionAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except QuestionInvalidReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete("/questions/{question_id}", response_model=DeleteQuestionResponse)
def delete_question(
    question_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: QuestionIngestionService = Depends(get_question_service),
) -> DeleteQuestionResponse:
    """Delete an owned question from the Question Bank."""
    try:
        return service.delete_question(question_id=question_id, user_id=current_user.id)
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except QuestionAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
