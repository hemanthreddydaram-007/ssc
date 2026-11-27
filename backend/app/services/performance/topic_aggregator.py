from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.assessment import Attempt
from app.models.performance import TopicPerformance, TopicPerformanceSnapshot
from app.repositories.performance_repo import PerformanceRepository
from app.schemas.performance import (
    AttemptAnalysisOut,
    LinkedNoteRefOut,
    PerformanceOverviewOut,
    TopicAttemptDeltaOut,
    TopicClassificationOut,
    TopicPerformanceListResponse,
    TopicPerformanceOut,
    TopicTrendPointOut,
    TopicTrendsOut,
)
from app.services.performance.error_classifier import ErrorClassifierService
from app.services.performance.metrics_calculator import (
    MIN_TOPIC_SAMPLE_SIZE,
    classify_topic_status,
    compute_accuracy_percent,
    compute_attempt_topic_stats,
    detect_speed_accuracy_anomalies,
    resolve_speed_target_ms,
    to_topic_classifications_out,
)
from app.services.performance.revision_scheduler import RevisionSchedulerService


class PerformanceNotFoundError(Exception):
    """Raised when an attempt or topic cannot be found."""


class PerformanceAccessDeniedError(Exception):
    """Raised when a user requests analytics for a resource owned by another user."""


class PerformanceConflictError(Exception):
    """Raised when analytics are requested for an in-progress attempt."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _to_topic_performance_out(
    tp: TopicPerformance,
    *,
    topic_name: str,
) -> TopicPerformanceOut:
    acc_delta: Decimal | None = None
    if tp.previous_accuracy_percent is not None:
        acc_delta = Decimal(tp.accuracy_percent) - Decimal(tp.previous_accuracy_percent)
    time_delta: int | None = None
    if tp.previous_average_time_ms is not None:
        time_delta = int(tp.average_time_ms) - int(tp.previous_average_time_ms)

    return TopicPerformanceOut(
        id=tp.id,
        topic_id=tp.topic_id,
        topic_name=topic_name,
        subject_code=tp.subject_code,
        attempt_count=tp.attempt_count,
        question_count=tp.question_count,
        answered_count=tp.answered_count,
        correct_count=tp.correct_count,
        timed_out_count=tp.timed_out_count,
        skipped_count=tp.skipped_count,
        accuracy_percent=Decimal(tp.accuracy_percent),
        average_time_ms=int(tp.average_time_ms),
        classification_status=tp.classification_status,  # type: ignore[arg-type]
        min_required=MIN_TOPIC_SAMPLE_SIZE,
        latest_attempt_id=tp.latest_attempt_id,
        previous_accuracy_percent=(
            Decimal(tp.previous_accuracy_percent)
            if tp.previous_accuracy_percent is not None
            else None
        ),
        previous_average_time_ms=(
            int(tp.previous_average_time_ms)
            if tp.previous_average_time_ms is not None
            else None
        ),
        accuracy_delta_percent=acc_delta,
        average_time_delta_ms=time_delta,
        updated_at=tp.updated_at,
    )


class TopicAggregatorService:
    """Computes attempt-level analytics and maintains idempotent cross-attempt aggregates."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = PerformanceRepository(db)
        self._error_classifier = ErrorClassifierService()
        self._revision_scheduler = RevisionSchedulerService(db)

    def sync_on_attempt_submitted(self, attempt_or_id: Attempt | UUID) -> None:
        """Idempotently record snapshots, cumulative topic stats, errors, and revisions."""
        attempt = (
            attempt_or_id
            if isinstance(attempt_or_id, Attempt)
            else self._repo.get_attempt(attempt_or_id)
        )
        if attempt is None or attempt.status == "in_progress":
            return

        pairs = self._repo.list_attempt_responses(attempt.id)
        if not pairs:
            return

        # Persist error classifications idempotently
        error_records, _patterns = self._error_classifier.classify_attempt(
            attempt=attempt, pairs=pairs
        )
        raw_topic_ids = {r.topic_id for r in error_records if r.topic_id is not None}
        valid_topic_ids = self._repo.list_existing_topic_ids(raw_topic_ids)
        for rec in error_records:
            if rec.topic_id is not None and rec.topic_id not in valid_topic_ids:
                rec.topic_id = None
        self._repo.replace_error_classifications(attempt.id, error_records)

        # Idempotent snapshot check: skip aggregate updates if already snapshotted
        existing_snapshots = self._repo.list_snapshots_for_attempt(attempt.id)
        if existing_snapshots:
            self._repo.commit()
            return

        aggregates = compute_attempt_topic_stats(attempt=attempt, pairs=pairs)
        agg_topic_ids = {agg.topic_id for agg in aggregates if agg.topic_id is not None}
        existing_topic_ids = self._repo.list_existing_topic_ids(agg_topic_ids)
        recorded_at = attempt.submitted_at or utcnow()
        speed_target_ms = resolve_speed_target_ms(attempt)

        # Group aggregates by topic_id (if multiple subjects somehow shared a topic, collapse)
        by_topic_id: dict[UUID, list] = {}
        for agg in aggregates:
            if agg.topic_id is None or agg.topic_id not in existing_topic_ids:
                continue
            by_topic_id.setdefault(agg.topic_id, []).append(agg)

        for topic_id, topic_aggs in by_topic_id.items():
            q_cnt = sum(a.question_count for a in topic_aggs)
            ans_cnt = sum(a.answered_count for a in topic_aggs)
            cor_cnt = sum(a.correct_count for a in topic_aggs)
            to_cnt = sum(a.timed_out_count for a in topic_aggs)
            skip_cnt = sum(a.skipped_count for a in topic_aggs)
            weighted_time_sum = sum(a.average_time_ms * a.answered_count for a in topic_aggs)
            avg_ms = round(weighted_time_sum / ans_cnt) if ans_cnt > 0 else 0
            acc = compute_accuracy_percent(cor_cnt, ans_cnt) or Decimal("0.00")
            subject_code = topic_aggs[0].subject_code

            snapshot = TopicPerformanceSnapshot(
                user_id=attempt.user_id,
                attempt_id=attempt.id,
                topic_id=topic_id,
                question_count=q_cnt,
                answered_count=ans_cnt,
                correct_count=cor_cnt,
                timed_out_count=to_cnt,
                accuracy_percent=acc,
                average_time_ms=avg_ms,
                recorded_at=recorded_at,
            )
            self._repo.add(snapshot)
            self._repo.flush()

            snapshots = self._repo.list_snapshots_for_user_topic(attempt.user_id, topic_id)
            cum_attempts = len(snapshots)
            cum_questions = sum(s.question_count for s in snapshots)
            cum_answered = sum(s.answered_count for s in snapshots)
            cum_correct = sum(s.correct_count for s in snapshots)
            cum_timed_out = sum(s.timed_out_count for s in snapshots)
            cum_time_weighted = sum(int(s.average_time_ms) * s.answered_count for s in snapshots)
            cum_avg_ms = round(cum_time_weighted / cum_answered) if cum_answered > 0 else 0
            cum_acc = compute_accuracy_percent(cum_correct, cum_answered)
            cum_status = classify_topic_status(
                question_count=cum_questions,
                answered_count=cum_answered,
                accuracy_percent=cum_acc,
                average_time_ms=cum_avg_ms,
                speed_target_ms=speed_target_ms,
            )

            tp = self._repo.get_topic_performance(attempt.user_id, topic_id)
            if tp is None:
                tp = TopicPerformance(
                    user_id=attempt.user_id,
                    topic_id=topic_id,
                    subject_code=subject_code,
                    attempt_count=cum_attempts,
                    question_count=cum_questions,
                    answered_count=cum_answered,
                    correct_count=cum_correct,
                    timed_out_count=cum_timed_out,
                    skipped_count=skip_cnt,
                    accuracy_percent=cum_acc or Decimal("0.00"),
                    average_time_ms=cum_avg_ms,
                    classification_status=cum_status,
                    latest_attempt_id=attempt.id,
                    previous_accuracy_percent=None,
                    previous_average_time_ms=None,
                )
                self._repo.add(tp)
            else:
                if tp.latest_attempt_id != attempt.id:
                    tp.previous_accuracy_percent = tp.accuracy_percent
                    tp.previous_average_time_ms = tp.average_time_ms
                tp.subject_code = subject_code
                tp.attempt_count = cum_attempts
                tp.question_count = cum_questions
                tp.answered_count = cum_answered
                tp.correct_count = cum_correct
                tp.timed_out_count = cum_timed_out
                tp.skipped_count = int(tp.skipped_count or 0) + skip_cnt
                tp.accuracy_percent = cum_acc or Decimal("0.00")
                tp.average_time_ms = cum_avg_ms
                tp.classification_status = cum_status
                tp.latest_attempt_id = attempt.id
                tp.updated_at = utcnow()

            self._revision_scheduler.sync_topic_revision(
                user_id=attempt.user_id,
                topic_id=topic_id,
                attempt_id=attempt.id,
                status=cum_status,
            )

        self._repo.commit()

    def _load_submitted_attempt(self, attempt_id: UUID, user_id: UUID) -> Attempt:
        attempt = self._repo.get_attempt(attempt_id)
        if attempt is None:
            raise PerformanceNotFoundError(f"Attempt '{attempt_id}' not found")
        if attempt.user_id != user_id:
            raise PerformanceAccessDeniedError("You do not have access to this attempt")
        if attempt.status == "in_progress":
            raise PerformanceConflictError(
                "ATTEMPT_IN_PROGRESS",
                "Analytics are unavailable until the attempt is submitted.",
            )
        return attempt

    def analyze_attempt(self, *, attempt_id: UUID, user_id: UUID) -> AttemptAnalysisOut:
        """Build speed/accuracy anomalies, error patterns, topic status, and deltas."""
        attempt = self._load_submitted_attempt(attempt_id, user_id)
        pairs = self._repo.list_attempt_responses(attempt.id)

        anomalies = detect_speed_accuracy_anomalies(attempt=attempt, pairs=pairs)
        _records, error_patterns = self._error_classifier.classify_attempt(
            attempt=attempt, pairs=pairs
        )
        aggregates = compute_attempt_topic_stats(attempt=attempt, pairs=pairs)
        classifications: list[TopicClassificationOut] = to_topic_classifications_out(aggregates)

        comparison_to_previous: list[TopicAttemptDeltaOut] = []
        seen_topics: set[UUID] = set()
        for agg in aggregates:
            if agg.topic_id is None or agg.topic_id in seen_topics:
                continue
            seen_topics.add(agg.topic_id)
            prev = self._repo.get_previous_topic_snapshot(
                user_id=user_id,
                topic_id=agg.topic_id,
                exclude_attempt_id=attempt.id,
                before_time=attempt.submitted_at,
            )
            if prev is None:
                continue
            curr_acc = agg.accuracy_percent or Decimal("0.00")
            prev_acc = Decimal(prev.accuracy_percent)
            comparison_to_previous.append(
                TopicAttemptDeltaOut(
                    topic_id=agg.topic_id,
                    topic_name=agg.topic_name,
                    subject_code=agg.subject_code,
                    previous_attempt_id=prev.attempt_id,
                    current_accuracy_percent=curr_acc,
                    previous_accuracy_percent=prev_acc,
                    accuracy_delta_percent=curr_acc - prev_acc,
                    current_average_time_ms=agg.average_time_ms,
                    previous_average_time_ms=int(prev.average_time_ms),
                    average_time_delta_ms=agg.average_time_ms - int(prev.average_time_ms),
                )
            )

        return AttemptAnalysisOut(
            attempt_id=attempt.id,
            test_id=attempt.test_id,
            speed_accuracy_anomalies=anomalies,
            error_patterns=error_patterns,
            topic_classifications=classifications,
            comparison_to_previous=comparison_to_previous,
        )

    def list_topics(
        self, *, user_id: UUID, subject_code: str | None = None
    ) -> TopicPerformanceListResponse:
        rows = self._repo.list_topic_performances(user_id, subject_code=subject_code)
        items = [_to_topic_performance_out(tp, topic_name=topic.name) for tp, topic in rows]
        return TopicPerformanceListResponse(items=items, total=len(items))

    def get_overview(self, *, user_id: UUID) -> PerformanceOverviewOut:
        attempts = self._repo.list_submitted_attempts(user_id)
        total_attempts = len(attempts)
        total_correct = sum(a.correct_count for a in attempts)
        total_answered = sum(a.correct_count + a.incorrect_count for a in attempts)
        overall_acc = compute_accuracy_percent(total_correct, total_answered)

        total_time_weighted = 0
        total_answered_for_time = 0
        for a in attempts:
            pairs = self._repo.list_attempt_responses(a.id)
            for resp, _tq in pairs:
                if resp.status == "answered":
                    total_time_weighted += min(max(0, int(resp.time_spent_ms or 0)), 300_000)
                    total_answered_for_time += 1
        overall_avg_ms = (
            round(total_time_weighted / total_answered_for_time)
            if total_answered_for_time > 0
            else 0
        )

        rows = self._repo.list_topic_performances(user_id)
        strong: list[TopicPerformanceOut] = []
        weak: list[TopicPerformanceOut] = []
        developing: list[TopicPerformanceOut] = []
        insufficient: list[TopicPerformanceOut] = []
        recent_deltas: list[TopicAttemptDeltaOut] = []

        for tp, topic in rows:
            item = _to_topic_performance_out(tp, topic_name=topic.name)
            if item.classification_status == "strong":
                strong.append(item)
            elif item.classification_status == "needs_practice":
                weak.append(item)
            elif item.classification_status == "developing":
                developing.append(item)
            else:
                insufficient.append(item)

            if item.previous_accuracy_percent is not None:
                recent_deltas.append(
                    TopicAttemptDeltaOut(
                        topic_id=item.topic_id,
                        topic_name=item.topic_name,
                        subject_code=item.subject_code,
                        previous_attempt_id=None,
                        current_accuracy_percent=item.accuracy_percent,
                        previous_accuracy_percent=item.previous_accuracy_percent,
                        accuracy_delta_percent=item.accuracy_delta_percent,
                        current_average_time_ms=item.average_time_ms,
                        previous_average_time_ms=item.previous_average_time_ms,
                        average_time_delta_ms=item.average_time_delta_ms,
                    )
                )

        due_revisions = self._revision_scheduler.list_revisions(
            user_id, status_filter="due"
        ).items

        return PerformanceOverviewOut(
            total_attempts=total_attempts,
            overall_accuracy_percent=overall_acc,
            overall_avg_time_ms=overall_avg_ms,
            strong_topics=strong,
            weak_topics=weak,
            developing_topics=developing,
            insufficient_data_topics=insufficient,
            recent_improvement_deltas=recent_deltas,
            due_revisions=due_revisions,
        )

    def get_topic_trends(self, *, user_id: UUID, topic_id: UUID) -> TopicTrendsOut:
        topic = self._repo.get_topic(topic_id)
        if topic is None:
            raise PerformanceNotFoundError(f"Topic '{topic_id}' not found")

        tp = self._repo.get_topic_performance(user_id, topic_id)
        trend_rows = self._repo.list_topic_trend_rows(user_id, topic_id)

        points = [
            TopicTrendPointOut(
                attempt_id=attempt.id,
                test_title=test.title,
                submitted_at=attempt.submitted_at or snap.recorded_at,
                question_count=snap.question_count,
                answered_count=snap.answered_count,
                correct_count=snap.correct_count,
                timed_out_count=snap.timed_out_count,
                accuracy_percent=Decimal(snap.accuracy_percent),
                average_time_ms=int(snap.average_time_ms),
            )
            for snap, attempt, test in trend_rows
        ]

        notes = self._repo.list_notes_for_topics(user_id, [topic_id])
        linked_notes = [
            LinkedNoteRefOut(
                id=n.id,
                title=n.title,
                note_type=n.note_type,
                document_id=n.document_id,
            )
            for n in notes
        ]

        return TopicTrendsOut(
            topic_id=topic.id,
            topic_name=topic.name,
            subject_code=topic.subject_code,
            classification_status=(
                tp.classification_status if tp is not None else "insufficient_data"  # type: ignore[arg-type]
            ),
            question_count=tp.question_count if tp is not None else 0,
            min_required=MIN_TOPIC_SAMPLE_SIZE,
            points=points,
            recommended_notes=linked_notes,
        )


def on_attempt_submitted(db: Session, attempt_or_id: Attempt | UUID) -> None:
    """Post-submit hook entrypoint for Assessment AttemptEngine."""
    TopicAggregatorService(db).sync_on_attempt_submitted(attempt_or_id)
