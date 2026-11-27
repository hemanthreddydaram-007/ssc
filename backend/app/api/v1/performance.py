from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.ai.provider import LLMProvider, get_llm_provider
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.performance import (
    AttemptAnalysisOut,
    ImprovementPlanOut,
    ImprovementPlanRequest,
    PerformanceOverviewOut,
    RevisionItemOut,
    RevisionListResponse,
    RevisionUpdateRequest,
    TargetedPracticeRequest,
    TargetedPracticeResponse,
    TopicPerformanceListResponse,
    TopicTrendsOut,
)
from app.services.performance.revision_scheduler import (
    RevisionAccessDeniedError,
    RevisionNotFoundError,
    RevisionSchedulerService,
)
from app.services.performance.rule_planner import RulePlannerService
from app.services.performance.targeted_practice import (
    TargetedPracticeService,
    TargetedPracticeValidationError,
)
from app.services.performance.topic_aggregator import (
    PerformanceAccessDeniedError,
    PerformanceConflictError,
    PerformanceNotFoundError,
    TopicAggregatorService,
)

router = APIRouter(tags=["performance"])


def _conflict_response(exc: PerformanceConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": exc.detail, "code": exc.code},
    )


@router.get("/attempts/{attempt_id}/analysis", response_model=AttemptAnalysisOut)
def get_attempt_analysis(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AttemptAnalysisOut | JSONResponse:
    """Return speed/accuracy anomalies, tentative error patterns, and topic classifications."""
    try:
        return TopicAggregatorService(db).analyze_attempt(
            attempt_id=attempt_id, user_id=current_user.id
        )
    except PerformanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PerformanceAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        return _conflict_response(exc)


@router.post(
    "/attempts/{attempt_id}/improvement-plan",
    response_model=ImprovementPlanOut,
)
def generate_improvement_plan(
    attempt_id: UUID,
    payload: ImprovementPlanRequest = ImprovementPlanRequest(),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> ImprovementPlanOut | JSONResponse:
    """Create or return a rule-based improvement plan with optional grounded AI coaching."""
    try:
        return RulePlannerService(db).get_or_create_plan(
            attempt_id=attempt_id,
            user_id=current_user.id,
            payload=payload,
            llm_provider=llm_provider,
        )
    except PerformanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PerformanceAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        return _conflict_response(exc)


@router.get(
    "/attempts/{attempt_id}/improvement-plan",
    response_model=ImprovementPlanOut,
)
def get_improvement_plan(
    attempt_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImprovementPlanOut | JSONResponse:
    """Retrieve the latest saved improvement plan for a submitted attempt."""
    try:
        return RulePlannerService(db).get_saved_plan(
            attempt_id=attempt_id, user_id=current_user.id
        )
    except PerformanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PerformanceAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except PerformanceConflictError as exc:
        return _conflict_response(exc)


@router.get("/performance/overview", response_model=PerformanceOverviewOut)
def get_performance_overview(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PerformanceOverviewOut:
    """Return cross-attempt performance overview for Screen 10."""
    return TopicAggregatorService(db).get_overview(user_id=current_user.id)


@router.get("/performance/topics", response_model=TopicPerformanceListResponse)
def list_topic_performance(
    subject_code: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopicPerformanceListResponse:
    """List cumulative topic performance metrics for the current user."""
    return TopicAggregatorService(db).list_topics(
        user_id=current_user.id, subject_code=subject_code
    )


@router.get("/performance/topics/{topic_id}/trends", response_model=TopicTrendsOut)
def get_topic_trends(
    topic_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopicTrendsOut:
    """Return cross-attempt accuracy and speed trend series for a single topic."""
    try:
        return TopicAggregatorService(db).get_topic_trends(
            user_id=current_user.id, topic_id=topic_id
        )
    except PerformanceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/performance/targeted-practice",
    response_model=TargetedPracticeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_targeted_practice(
    payload: TargetedPracticeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetedPracticeResponse:
    """Build a targeted practice test from weak topics and return linked revision notes."""
    try:
        return TargetedPracticeService(db).create_targeted_practice(
            user_id=current_user.id, payload=payload
        )
    except TargetedPracticeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/performance/revisions", response_model=RevisionListResponse)
def list_revision_items(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RevisionListResponse:
    """List scheduled revision items for the current user."""
    return RevisionSchedulerService(db).list_revisions(
        user_id=current_user.id, status_filter=status_filter
    )


@router.patch("/performance/revisions/{item_id}", response_model=RevisionItemOut)
def update_revision_item(
    item_id: UUID,
    payload: RevisionUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RevisionItemOut:
    """Mark a revision schedule item as completed or dismissed."""
    try:
        return RevisionSchedulerService(db).update_revision_status(
            user_id=current_user.id, item_id=item_id, new_status=payload.status
        )
    except RevisionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RevisionAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
