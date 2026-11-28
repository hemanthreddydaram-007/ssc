from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.assessment import Attempt
from app.models.document import Document, ProcessingJob
from app.models.learning import Note
from app.repositories.job_repo import (
    DEFAULT_STALE_JOB_TIMEOUT,
    _job_to_out,
    recover_stale_jobs,
)
from app.repositories.question_repo import QuestionRepository
from app.schemas.attempt import AttemptSummaryOut
from app.schemas.document import DocumentOut
from app.schemas.job import ProcessingJobOut
from app.schemas.performance import RevisionItemOut, TopicPerformanceOut
from app.services.assessment.attempt_engine import AttemptEngine
from app.services.assessment.scoring_service import AttemptPostSubmitHook
from app.services.assessment.timer_service import ClockFn, get_clock
from app.services.performance.topic_aggregator import TopicAggregatorService, on_attempt_submitted

router = APIRouter(tags=["dashboard"])


class DashboardTotalsOut(BaseModel):
    documents_count: int
    notes_count: int
    questions_count: int
    completed_attempts_count: int


class DashboardSummaryOut(BaseModel):
    continue_attempt: AttemptSummaryOut | None = None
    recent_documents: list[DocumentOut]
    active_jobs: list[ProcessingJobOut]
    recent_attempts: list[AttemptSummaryOut]
    weak_topics: list[TopicPerformanceOut]
    due_revisions: list[RevisionItemOut]
    totals: DashboardTotalsOut


def get_post_submit_hook() -> AttemptPostSubmitHook:
    """Wire M7 TopicAggregator post-submit hook."""
    return on_attempt_submitted


@router.get("/dashboard", response_model=DashboardSummaryOut)
def get_dashboard_summary(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: ClockFn = Depends(get_clock),
    post_submit_hook: AttemptPostSubmitHook = Depends(get_post_submit_hook),
) -> DashboardSummaryOut:
    """Return aggregated live student dashboard data without fake metrics."""
    user_id = current_user.id

    recent_docs = (
        db.execute(
            select(Document)
            .where(Document.user_id == user_id, Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc())
            .limit(5)
        )
        .scalars()
        .all()
    )

    recover_stale_jobs(
        db, stale_after=DEFAULT_STALE_JOB_TIMEOUT, ignore_heartbeats=False
    )

    active_job_rows = (
        db.execute(
            select(ProcessingJob, Document.title)
            .join(Document, ProcessingJob.document_id == Document.id)
            .where(
                Document.user_id == user_id,
                Document.deleted_at.is_(None),
                ProcessingJob.status.in_(("queued", "running")),
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(5)
        )
        .all()
    )

    attempts_list = AttemptEngine(
        db, clock=clock, post_submit_hook=post_submit_hook
    ).list_attempts(user_id=user_id, limit=10, offset=0)
    continue_attempt = next(
        (item for item in attempts_list.items if item.status == "in_progress"),
        None,
    )
    recent_attempts = [
        item for item in attempts_list.items if item.status != "in_progress"
    ][:5]

    overview = TopicAggregatorService(db).get_overview(user_id=user_id)

    documents_count = int(
        db.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.user_id == user_id, Document.deleted_at.is_(None))
        ).scalar_one()
    )
    notes_count = int(
        db.execute(
            select(func.count())
            .select_from(Note)
            .join(Document, Note.document_id == Document.id)
            .where(Document.user_id == user_id, Document.deleted_at.is_(None))
        ).scalar_one()
    )
    _, _, questions_count = QuestionRepository(db).list_questions_for_user(
        user_id=user_id, limit=1, offset=0
    )

    completed_attempts_count = int(
        db.execute(
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.user_id == user_id, Attempt.status != "in_progress")
        ).scalar_one()
    )

    return DashboardSummaryOut(
        continue_attempt=continue_attempt,
        recent_documents=[DocumentOut.model_validate(doc) for doc in recent_docs],
        active_jobs=[
            _job_to_out(job, document_title=doc_title) for job, doc_title in active_job_rows
        ],
        recent_attempts=recent_attempts,
        weak_topics=overview.weak_topics[:5],
        due_revisions=overview.due_revisions[:5],
        totals=DashboardTotalsOut(
            documents_count=documents_count,
            notes_count=notes_count,
            questions_count=questions_count,
            completed_attempts_count=completed_attempts_count,
        ),
    )
