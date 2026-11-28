from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.test import (
    TestCreateRequest,
    TestListResponse,
    TestOut,
    TestPreviewRequest,
    TestPreviewResponse,
)
from app.services.assessment.test_builder import (
    TestAccessDeniedError,
    TestBuilderService,
    TestBuildValidationError,
    TestNotFoundError,
)
from app.services.assessment.timer_service import ClockFn, get_clock
from app.services.performance.topic_aggregator import on_attempt_submitted

router = APIRouter(prefix="/tests", tags=["tests"])


def get_test_builder_service(
    db: Session = Depends(get_db),
    clock: ClockFn = Depends(get_clock),
) -> TestBuilderService:
    """Build a TestBuilderService bound to the current DB session."""
    return TestBuilderService(db, clock=clock, post_submit_hook=on_attempt_submitted)


@router.post("/preview", response_model=TestPreviewResponse)
def preview_test(
    payload: TestPreviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: TestBuilderService = Depends(get_test_builder_service),
) -> TestPreviewResponse:
    """Preview matching question availability before building a test."""
    return service.preview(current_user.id, payload)


@router.post("", response_model=TestOut, status_code=status.HTTP_201_CREATED)
def create_test(
    payload: TestCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: TestBuilderService = Depends(get_test_builder_service),
) -> TestOut:
    """Create a test and freeze immutable question snapshots."""
    try:
        return service.create_test(current_user.id, payload)
    except TestBuildValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("", response_model=TestListResponse)
def list_tests(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    service: TestBuilderService = Depends(get_test_builder_service),
) -> TestListResponse:
    """List tests created by the current user."""
    return service.list_tests(current_user.id, limit=limit, offset=offset)


@router.get("/{test_id}", response_model=TestOut)
def get_test(
    test_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TestBuilderService = Depends(get_test_builder_service),
) -> TestOut:
    """Fetch metadata and settings for an owned test (never exposes answer keys)."""
    try:
        return service.get_test(test_id, current_user.id)
    except TestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TestAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
