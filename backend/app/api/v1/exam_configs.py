from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.repositories.exam_config_repo import ExamConfigRepository
from app.schemas.exam_config import (
    ExamConfigCreateRequest,
    ExamConfigListResponse,
    ExamConfigOut,
)
from app.services.assessment.exam_config_service import (
    ExamConfigAlreadyExistsError,
    ExamConfigNotFoundError,
    ExamConfigService,
)

router = APIRouter(prefix="/exam-configs", tags=["exam-configs"])


def get_exam_config_service(db: Session = Depends(get_db)) -> ExamConfigService:
    """Construct an `ExamConfigService` bound to the request DB session."""
    return ExamConfigService(ExamConfigRepository(db))


@router.get("", response_model=ExamConfigListResponse)
def list_exam_configs(
    service: ExamConfigService = Depends(get_exam_config_service),
    _: CurrentUser = Depends(get_current_user),
) -> ExamConfigListResponse:
    """List available exam configuration packs."""
    return service.list_exam_configs()


@router.get("/{exam_code}", response_model=ExamConfigOut)
def get_exam_config(
    exam_code: str,
    service: ExamConfigService = Depends(get_exam_config_service),
    _: CurrentUser = Depends(get_current_user),
) -> ExamConfigOut:
    """Fetch a single exam configuration pack by `exam_code`."""
    try:
        return service.get_exam_config_by_code(exam_code)
    except ExamConfigNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("", response_model=ExamConfigOut, status_code=status.HTTP_201_CREATED)
def create_exam_config(
    payload: ExamConfigCreateRequest,
    service: ExamConfigService = Depends(get_exam_config_service),
    _: CurrentUser = Depends(get_current_user),
) -> ExamConfigOut:
    """Create a custom versioned exam configuration pack."""
    try:
        return service.create_exam_config(payload)
    except ExamConfigAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
