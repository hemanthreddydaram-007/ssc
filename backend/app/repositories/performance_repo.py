from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.assessment import Attempt, Response, Test, TestQuestion
from app.models.document import Document
from app.models.learning import Note, Topic
from app.models.performance import (
    AttemptErrorClassification,
    ImprovementPlan,
    RevisionScheduleItem,
    TopicPerformance,
    TopicPerformanceSnapshot,
)


class PerformanceRepository:
    """Data-access layer for analytics, snapshots, error classifications, plans, and revisions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_attempt(self, attempt_id: UUID) -> Attempt | None:
        return self._db.get(Attempt, attempt_id)

    def get_test(self, test_id: UUID) -> Test | None:
        return self._db.get(Test, test_id)

    def get_topic(self, topic_id: UUID) -> Topic | None:
        return self._db.get(Topic, topic_id)

    def list_existing_topic_ids(self, topic_ids: set[UUID]) -> set[UUID]:
        if not topic_ids:
            return set()
        stmt = select(Topic.id).where(Topic.id.in_(list(topic_ids)))
        return set(self._db.execute(stmt).scalars().all())

    def get_topic_names_map(self, topic_ids: set[UUID]) -> dict[UUID, Topic]:
        if not topic_ids:
            return {}
        stmt = select(Topic).where(Topic.id.in_(list(topic_ids)))
        topics = self._db.execute(stmt).scalars().all()
        return {t.id: t for t in topics}

    def list_attempt_responses(self, attempt_id: UUID) -> list[tuple[Response, TestQuestion]]:
        stmt = (
            select(Response, TestQuestion)
            .join(TestQuestion, TestQuestion.id == Response.test_question_id)
            .where(Response.attempt_id == attempt_id)
            .order_by(TestQuestion.display_order.asc())
        )
        return [(row[0], row[1]) for row in self._db.execute(stmt).all()]

    def list_submitted_attempts(self, user_id: UUID) -> list[Attempt]:
        stmt = (
            select(Attempt)
            .where(
                Attempt.user_id == user_id,
                Attempt.status.in_(["submitted", "timed_out_submitted"]),
            )
            .order_by(Attempt.submitted_at.desc(), Attempt.started_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_snapshots_for_attempt(self, attempt_id: UUID) -> list[TopicPerformanceSnapshot]:
        stmt = select(TopicPerformanceSnapshot).where(
            TopicPerformanceSnapshot.attempt_id == attempt_id
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_snapshots_for_user_topic(
        self, user_id: UUID, topic_id: UUID
    ) -> list[TopicPerformanceSnapshot]:
        stmt = (
            select(TopicPerformanceSnapshot)
            .where(
                TopicPerformanceSnapshot.user_id == user_id,
                TopicPerformanceSnapshot.topic_id == topic_id,
            )
            .order_by(TopicPerformanceSnapshot.recorded_at.asc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_topic_trend_rows(
        self, user_id: UUID, topic_id: UUID
    ) -> list[tuple[TopicPerformanceSnapshot, Attempt, Test]]:
        stmt = (
            select(TopicPerformanceSnapshot, Attempt, Test)
            .join(Attempt, Attempt.id == TopicPerformanceSnapshot.attempt_id)
            .join(Test, Test.id == Attempt.test_id)
            .where(
                TopicPerformanceSnapshot.user_id == user_id,
                TopicPerformanceSnapshot.topic_id == topic_id,
            )
            .order_by(TopicPerformanceSnapshot.recorded_at.asc(), Attempt.started_at.asc())
        )
        return [(row[0], row[1], row[2]) for row in self._db.execute(stmt).all()]

    def get_previous_topic_snapshot(
        self,
        *,
        user_id: UUID,
        topic_id: UUID,
        exclude_attempt_id: UUID,
        before_time: datetime | None,
    ) -> TopicPerformanceSnapshot | None:
        stmt = select(TopicPerformanceSnapshot).where(
            TopicPerformanceSnapshot.user_id == user_id,
            TopicPerformanceSnapshot.topic_id == topic_id,
            TopicPerformanceSnapshot.attempt_id != exclude_attempt_id,
        )
        if before_time is not None:
            stmt = stmt.where(TopicPerformanceSnapshot.recorded_at <= before_time)
        stmt = stmt.order_by(TopicPerformanceSnapshot.recorded_at.desc()).limit(1)
        return self._db.execute(stmt).scalar_one_or_none()

    def get_topic_performance(self, user_id: UUID, topic_id: UUID) -> TopicPerformance | None:
        stmt = select(TopicPerformance).where(
            TopicPerformance.user_id == user_id,
            TopicPerformance.topic_id == topic_id,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def list_topic_performances(
        self, user_id: UUID, *, subject_code: str | None = None
    ) -> list[tuple[TopicPerformance, Topic]]:
        stmt = (
            select(TopicPerformance, Topic)
            .join(Topic, Topic.id == TopicPerformance.topic_id)
            .where(TopicPerformance.user_id == user_id)
        )
        if subject_code:
            stmt = stmt.where(TopicPerformance.subject_code == subject_code)
        stmt = stmt.order_by(TopicPerformance.accuracy_percent.asc(), Topic.name.asc())
        return [(row[0], row[1]) for row in self._db.execute(stmt).all()]

    def replace_error_classifications(
        self, attempt_id: UUID, items: list[AttemptErrorClassification]
    ) -> None:
        self._db.execute(
            delete(AttemptErrorClassification).where(
                AttemptErrorClassification.attempt_id == attempt_id
            )
        )
        for item in items:
            self._db.add(item)

    def get_latest_improvement_plan(
        self, attempt_id: UUID, user_id: UUID
    ) -> ImprovementPlan | None:
        stmt = (
            select(ImprovementPlan)
            .where(
                ImprovementPlan.attempt_id == attempt_id,
                ImprovementPlan.user_id == user_id,
            )
            .order_by(ImprovementPlan.plan_version.desc(), ImprovementPlan.created_at.desc())
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def list_notes_for_topics(
        self, user_id: UUID, topic_ids: list[UUID]
    ) -> list[Note]:
        if not topic_ids:
            return []
        stmt = (
            select(Note)
            .join(Document, Document.id == Note.document_id)
            .where(
                Document.user_id == user_id,
                Document.deleted_at.is_(None),
                Note.topic_id.in_(topic_ids),
                Note.status == "ready",
            )
            .order_by(Note.created_at.desc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def get_open_revision_for_topic(
        self, user_id: UUID, topic_id: UUID
    ) -> RevisionScheduleItem | None:
        stmt = (
            select(RevisionScheduleItem)
            .where(
                RevisionScheduleItem.user_id == user_id,
                RevisionScheduleItem.topic_id == topic_id,
                RevisionScheduleItem.status == "due",
            )
            .order_by(RevisionScheduleItem.created_at.desc())
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def list_revisions(
        self,
        user_id: UUID,
        *,
        status_filter: str | None = None,
    ) -> list[tuple[RevisionScheduleItem, Topic]]:
        stmt = (
            select(RevisionScheduleItem, Topic)
            .join(Topic, Topic.id == RevisionScheduleItem.topic_id)
            .where(RevisionScheduleItem.user_id == user_id)
        )
        if status_filter:
            stmt = stmt.where(RevisionScheduleItem.status == status_filter)
        stmt = stmt.order_by(
            RevisionScheduleItem.priority.asc(),
            RevisionScheduleItem.due_at.asc(),
        )
        return [(row[0], row[1]) for row in self._db.execute(stmt).all()]

    def get_revision_item(self, item_id: UUID) -> RevisionScheduleItem | None:
        return self._db.get(RevisionScheduleItem, item_id)

    def add(self, instance: object) -> None:
        self._db.add(instance)

    def flush(self) -> None:
        self._db.flush()

    def commit(self) -> None:
        self._db.commit()
