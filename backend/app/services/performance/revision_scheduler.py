from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.performance import RevisionScheduleItem
from app.repositories.performance_repo import PerformanceRepository
from app.schemas.performance import (
    RevisionItemOut,
    RevisionListResponse,
    TopicClassificationStatus,
)


class RevisionNotFoundError(Exception):
    """Raised when a revision schedule item does not exist."""


class RevisionAccessDeniedError(Exception):
    """Raised when a user accesses another user's revision schedule item."""


class RevisionSchedulerService:
    """Lightweight MVP revision queue for weak and developing topics."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = PerformanceRepository(db)

    def sync_topic_revision(
        self,
        *,
        user_id: UUID,
        topic_id: UUID,
        attempt_id: UUID,
        status: TopicClassificationStatus,
    ) -> None:
        """Create, prioritize, or auto-complete a revision item based on topic status."""
        now = utcnow()
        existing = self._repo.get_open_revision_for_topic(user_id, topic_id)

        if status == "needs_practice":
            if existing is None:
                self._repo.add(
                    RevisionScheduleItem(
                        user_id=user_id,
                        topic_id=topic_id,
                        source_attempt_id=attempt_id,
                        reason_rule_id="RULE_CONCEPT_REVISION",
                        priority=1,
                        due_at=now,
                        status="due",
                    )
                )
            else:
                existing.source_attempt_id = attempt_id
                existing.reason_rule_id = "RULE_CONCEPT_REVISION"
                existing.priority = 1
                existing.due_at = now
        elif status == "developing":
            due_at = now + timedelta(days=2)
            if existing is None:
                self._repo.add(
                    RevisionScheduleItem(
                        user_id=user_id,
                        topic_id=topic_id,
                        source_attempt_id=attempt_id,
                        reason_rule_id="RULE_DEVELOPING_TOPIC",
                        priority=2,
                        due_at=due_at,
                        status="due",
                    )
                )
            else:
                existing.source_attempt_id = attempt_id
                existing.reason_rule_id = "RULE_DEVELOPING_TOPIC"
                existing.priority = min(existing.priority, 2)
        elif status == "strong" and existing is not None:
            existing.status = "completed"
            existing.completed_at = now

    def list_revisions(
        self,
        user_id: UUID,
        *,
        status_filter: str | None = None,
    ) -> RevisionListResponse:
        rows = self._repo.list_revisions(user_id, status_filter=status_filter)
        items = [
            RevisionItemOut(
                id=item.id,
                topic_id=item.topic_id,
                topic_name=topic.name,
                subject_code=topic.subject_code,
                source_attempt_id=item.source_attempt_id,
                reason_rule_id=item.reason_rule_id,
                priority=item.priority,
                due_at=item.due_at,
                status=item.status,
                completed_at=item.completed_at,
                created_at=item.created_at,
            )
            for item, topic in rows
        ]
        return RevisionListResponse(items=items, total=len(items))

    def update_revision_status(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
        new_status: str,
    ) -> RevisionItemOut:
        item = self._repo.get_revision_item(item_id)
        if item is None:
            raise RevisionNotFoundError(f"Revision item '{item_id}' not found")
        if item.user_id != user_id:
            raise RevisionAccessDeniedError("You do not have access to this revision item")

        topic = self._repo.get_topic(item.topic_id)
        item.status = new_status
        item.completed_at = utcnow() if new_status == "completed" else None
        self._repo.commit()

        return RevisionItemOut(
            id=item.id,
            topic_id=item.topic_id,
            topic_name=topic.name if topic else "Unknown Topic",
            subject_code=topic.subject_code if topic else "unknown",
            source_attempt_id=item.source_attempt_id,
            reason_rule_id=item.reason_rule_id,
            priority=item.priority,
            due_at=item.due_at,
            status=item.status,
            completed_at=item.completed_at,
            created_at=item.created_at,
        )
