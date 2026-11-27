from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assessment import Attempt, Response, Test, TestQuestion


class AttemptRepository:
    """Data-access layer for test attempts, test questions, and responses."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_test(self, test_id: UUID) -> Test | None:
        """Fetch a Test by ID."""
        return self._db.get(Test, test_id)

    def list_test_questions(self, test_id: UUID) -> list[TestQuestion]:
        """Fetch ordered TestQuestion snapshots for a test."""
        stmt = (
            select(TestQuestion)
            .where(TestQuestion.test_id == test_id)
            .order_by(TestQuestion.display_order.asc())
        )
        return list(self._db.execute(stmt).scalars().all())

    def get_attempt(self, attempt_id: UUID, *, for_update: bool = False) -> Attempt | None:
        """Fetch an Attempt by ID, optionally acquiring a row lock on supporting dialects."""
        stmt = select(Attempt).where(Attempt.id == attempt_id)
        if for_update:
            bind = self._db.get_bind()
            if bind is not None and bind.dialect.name != "sqlite":
                stmt = stmt.with_for_update()
        return self._db.execute(stmt).scalar_one_or_none()

    def list_attempts_for_user(
        self,
        user_id: UUID,
        *,
        test_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[tuple[Attempt, Test]]:
        """List attempts owned by `user_id` joined with their Test."""
        conditions = [Attempt.user_id == user_id]
        if test_id is not None:
            conditions.append(Attempt.test_id == test_id)
        stmt = (
            select(Attempt, Test)
            .join(Test, Test.id == Attempt.test_id)
            .where(*conditions)
            .order_by(Attempt.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in self._db.execute(stmt).all()]

    def create_attempt_with_responses(
        self,
        attempt: Attempt,
        responses: list[Response],
    ) -> Attempt:
        """Persist a new Attempt and its initialized Response rows."""
        self._db.add(attempt)
        self._db.flush()
        for resp in responses:
            resp.attempt_id = attempt.id
            self._db.add(resp)
        self._db.commit()
        self._db.refresh(attempt)
        return attempt

    def list_responses_with_questions(
        self, attempt_id: UUID
    ) -> list[tuple[Response, TestQuestion]]:
        """Return ordered `(Response, TestQuestion)` pairs for an attempt."""
        stmt = (
            select(Response, TestQuestion)
            .join(TestQuestion, TestQuestion.id == Response.test_question_id)
            .where(Response.attempt_id == attempt_id)
            .order_by(TestQuestion.display_order.asc())
        )
        return [(row[0], row[1]) for row in self._db.execute(stmt).all()]

    def get_response_by_id(self, attempt_id: UUID, response_id: UUID) -> Response | None:
        """Fetch a single Response belonging to `attempt_id`."""
        stmt = select(Response).where(
            Response.id == response_id,
            Response.attempt_id == attempt_id,
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def commit(self) -> None:
        """Commit staged changes."""
        self._db.commit()
