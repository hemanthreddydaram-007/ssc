from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.attempt import (
    AttemptCurrentOut,
    AttemptListResponse,
    AttemptResultsOut,
    AttemptSummaryOut,
    NavigateRequest,
    ResponseSaveOut,
    SaveResponseRequest,
    SelfReportOut,
    SelfReportRequest,
)
from app.services.assessment.attempt_engine import (
    AttemptAccessDeniedError,
    AttemptBadRequestError,
    AttemptConflictError,
    AttemptEngine,
    AttemptNotFoundError,
    AttemptValidationError,
)
from app.services.assessment.scoring_service import AttemptPostSubmitHook
from app.services.assessment.timer_service import ClockFn, get_clock
from app.services.performance.topic_aggregator import on_attempt_submitted

router = APIRouter(tags=["attempts"])


def get_post_submit_hook() -> AttemptPostSubmitHook:
    """Wire M7 TopicAggregator post-submit hook."""
    return on_attempt_submitted


def get_attempt_engine(
    db: Session = Depends(get_db),
    clock: ClockFn = Depends(get_clock),
    post_submit_hook: AttemptPostSubmitHook = Depends(get_post_submit_hook),
) -> AttemptEngine:
    """Build an AttemptEngine wired with server clock and post-submit hook."""
    return AttemptEngine(db, clock=clock, post_submit_hook=post_submit_hook)


def _conflict_response(exc: AttemptConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": exc.detail, "code": exc.code},
    )


@router.post(
    "/tests/{test_id}/start",
    response_model=AttemptCurrentOut,
    status_code=status.HTTP_201_CREATED,
)
def start_attempt(
    test_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    engine: AttemptEngine = Depends(get_attempt_engine),
) -> AttemptCurrentOut:
    """Start a new timed attempt for an owned test."""
    try:
        return engine.start_attempt(test_id=test_id, user_id=current_user.id)
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AttemptAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AttemptValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/attempts", response_model=AttemptListResponse)
def list_attempts(
    test_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    engine: AttemptEngine = Depends(get_attempt_engine),
) -> AttemptListResponse:
    """List test attempts belonging to the current user."""
    return engine.list_attempts(current_user.id, test_id=test_id, limit=limit, offset=offset)


@router.get("/attempts/{attempt_id}/current", response_model=AttemptCurrentOut)
def get_current_attempt_state(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    engine: AttemptEngine = Depends(get_attempt_engine),
) -> AttemptCurrentOut:
    """Return active attempt state and server-derived remaining time after expiry reconciliation."""
    try:
        return engine.get_current(attempt_id=attempt_id, user_id=current_user.id)
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AttemptAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/attempts/{attempt_id}/navigate", response_model=AttemptCurrentOut)
def navigate_attempt(
    attempt_id: UUID,
    payload: NavigateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    engine: AttemptEngine = Depends(get_attempt_engine),
) -> AttemptCurrentOut | JSONResponse:
    """Navigate between questions in Exam Simulation or Learning Mode."""
    try:
        return engine.navigate(
            attempt_id=attempt_id, user_id=current_user.id, payload=payload
        )
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AttemptAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AttemptBadRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AttemptValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AttemptConflictError as exc:
        return _conflict_response(exc)


@router.post("/attempts/{attempt_id}/responses", response_model=ResponseSaveOut)
def save_attempt_response(
    attempt_id: UUID,
    payload: SaveResponseRequest,
    current_user: CurrentUser = Depends(get_current_user),
    engine: AttemptEngine = Depends(get_attempt_engine),
) -> ResponseSaveOut | JSONResponse:
    """Save an answer, skip, or mark-for-review flag with server-authoritative timing."""
    try:
        return engine.save_response(
            attempt_id=attempt_id, user_id=current_user.id, payload=payload
        )
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AttemptAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AttemptBadRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AttemptValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except AttemptConflictError as exc:
        return _conflict_response(exc)


@router.patch(
    "/attempts/{attempt_id}/responses/{response_id}/self-report",
    response_model=SelfReportOut,
)
def save_response_self_report(
    attempt_id: UUID,
    response_id: UUID,
    payload: SelfReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    engine: AttemptEngine = Depends(get_attempt_engine),
) -> SelfReportOut:
    """Save optional confidence or mistake-reason self-report tags on a response."""
    try:
        return engine.save_self_report(
            attempt_id=attempt_id,
            response_id=response_id,
            user_id=current_user.id,
            payload=payload,
        )
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AttemptAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptSummaryOut)
def submit_attempt(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    engine: AttemptEngine = Depends(get_attempt_engine),
) -> AttemptSummaryOut:
    """Finalize and score an attempt idempotently."""
    try:
        return engine.submit_attempt(attempt_id=attempt_id, user_id=current_user.id)
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AttemptAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.get("/attempts/{attempt_id}/results", response_model=AttemptResultsOut)
def get_attempt_results(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    engine: AttemptEngine = Depends(get_attempt_engine),
) -> AttemptResultsOut | JSONResponse:
    """Return full graded results and explanations once the attempt is submitted."""
    try:
        return engine.get_results(attempt_id=attempt_id, user_id=current_user.id)
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AttemptAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AttemptConflictError as exc:
        return _conflict_response(exc)
