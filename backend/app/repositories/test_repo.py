from __future__ import annotations

from uuid import UUID

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.assessment import Attempt, Question, QuestionOption, Test, TestQuestion
from app.models.document import Document
from app.models.learning import Topic
from app.models.user import ExamConfig


class TestRepository:
    """Data-access layer for test construction, question pool selection, and test queries."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def exam_config_exists(self, exam_config_id: UUID) -> bool:
        """Return True if an ExamConfig with `exam_config_id` exists."""
        return self._db.get(ExamConfig, exam_config_id) is not None

    def query_candidate_questions(
        self,
        user_id: UUID,
        *,
        document_ids: list[UUID] | None = None,
        subject_codes: list[str] | None = None,
        topic_ids: list[UUID] | None = None,
        question_ids: list[UUID] | None = None,
        origin_mode: str = "mixed",
        include_needs_review: bool = False,
    ) -> list[tuple[Question, str | None, list[QuestionOption]]]:
        """Fetch user-owned eligible questions with topic names and ordered options."""
        user_test_question_ids = (
            select(TestQuestion.question_id)
            .join(Test, Test.id == TestQuestion.test_id)
            .where(Test.user_id == user_id, TestQuestion.question_id.is_not(None))
        )

        conditions = [
            or_(
                (Document.user_id == user_id) & (Document.deleted_at.is_(None)),
                (Question.document_id.is_(None))
                & or_(
                    Question.id.in_(user_test_question_ids),
                    cast(Question.correct_answer_data, String).contains(str(user_id)),
                ),
            )
        ]

        if include_needs_review:
            conditions.append(Question.validation_status.in_(["verified", "needs_review"]))
        else:
            conditions.append(Question.validation_status == "verified")

        if document_ids:
            conditions.append(Question.document_id.in_(document_ids))
        if subject_codes:
            conditions.append(Question.subject_code.in_(subject_codes))
        if topic_ids:
            conditions.append(Question.topic_id.in_(topic_ids))
        if question_ids:
            conditions.append(Question.id.in_(question_ids))
        if origin_mode == "extracted":
            conditions.append(Question.origin == "extracted")
        elif origin_mode == "generated":
            conditions.append(Question.origin == "generated")

        stmt = (
            select(Question, Topic.name)
            .outerjoin(Document, Document.id == Question.document_id)
            .outerjoin(Topic, Topic.id == Question.topic_id)
            .where(*conditions)
            .order_by(Question.created_at.asc(), Question.id.asc())
        )
        rows = self._db.execute(stmt).all()

        filtered: list[tuple[Question, str | None]] = []
        for question, topic_name in rows:
            if question.document_id is None:
                answer_data = question.correct_answer_data or {}
                if answer_data.get("owner_user_id") != str(user_id):
                    # Verify test ownership fallback
                    has_test = (
                        self._db.execute(
                            select(TestQuestion.id)
                            .join(Test, Test.id == TestQuestion.test_id)
                            .where(
                                TestQuestion.question_id == question.id,
                                Test.user_id == user_id,
                            )
                            .limit(1)
                        ).scalar_one_or_none()
                        is not None
                    )
                    if not has_test:
                        continue
            filtered.append((question, topic_name))

        if not filtered:
            return []

        q_ids = [q.id for q, _ in filtered]
        opt_stmt = (
            select(QuestionOption)
            .where(QuestionOption.question_id.in_(q_ids))
            .order_by(QuestionOption.display_order.asc(), QuestionOption.option_key.asc())
        )
        options_map: dict[UUID, list[QuestionOption]] = {}
        for opt in self._db.execute(opt_stmt).scalars().all():
            options_map.setdefault(opt.question_id, []).append(opt)

        return [(q, topic_name, options_map.get(q.id, [])) for q, topic_name in filtered]

    def create_test_with_questions(
        self,
        test: Test,
        test_questions: list[TestQuestion],
    ) -> Test:
        """Persist a Test and its immutable TestQuestion snapshots atomically."""
        self._db.add(test)
        self._db.flush()
        for tq in test_questions:
            tq.test_id = test.id
            self._db.add(tq)
        self._db.commit()
        self._db.refresh(test)
        return test

    def get_by_id(self, test_id: UUID) -> Test | None:
        """Fetch a Test by primary key."""
        return self._db.get(Test, test_id)

    def get_latest_attempts_map(self, test_ids: list[UUID], user_id: UUID) -> dict[UUID, Attempt]:
        """Return the most recent Attempt per test ID for `user_id`."""
        if not test_ids:
            return {}
        stmt = (
            select(Attempt)
            .where(Attempt.test_id.in_(test_ids), Attempt.user_id == user_id)
            .order_by(Attempt.started_at.desc())
        )
        latest: dict[UUID, Attempt] = {}
        for att in self._db.execute(stmt).scalars().all():
            latest.setdefault(att.test_id, att)
        return latest

    def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Test], int]:
        """Return paginated tests owned by `user_id`."""
        count_stmt = select(func.count(Test.id)).where(Test.user_id == user_id)
        total = int(self._db.execute(count_stmt).scalar_one())

        items_stmt = (
            select(Test)
            .where(Test.user_id == user_id)
            .order_by(Test.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(self._db.execute(items_stmt).scalars().all())
        return items, total
