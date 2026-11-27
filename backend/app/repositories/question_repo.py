from __future__ import annotations

from uuid import UUID

from sqlalchemy import String, cast, delete, or_, select, update
from sqlalchemy.orm import Session

from app.models.assessment import Question, QuestionOption, Test, TestQuestion
from app.models.document import Document
from app.models.learning import AIGenerationRun, Concept, Fact, Topic
from app.models.user import ExamConfig


class QuestionRepository:
    """Data-access layer for questions, options, and related knowledge scopes."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_document_for_ownership(self, document_id: UUID) -> Document | None:
        """Fetch an active (non-deleted) document by ID for ownership checks."""
        stmt = select(Document).where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def exam_config_exists(self, exam_config_id: UUID) -> bool:
        """Return True if the referenced ExamConfig exists."""
        return self._db.get(ExamConfig, exam_config_id) is not None

    def get_topic_by_id(self, topic_id: UUID) -> Topic | None:
        """Fetch a Topic by primary key."""
        return self._db.get(Topic, topic_id)

    def get_or_create_topic(
        self,
        *,
        subject_code: str,
        topic_name: str,
        exam_config_id: UUID | None = None,
    ) -> Topic | None:
        """Look up a topic by subject_code and slug/name, creating if needed."""
        cleaned = " ".join(topic_name.split()).strip()
        if not cleaned or cleaned.lower() == "unknown":
            return None
        slug = "-".join(
            part for part in "".join(ch if ch.isalnum() else " " for ch in cleaned.lower()).split()
        )[:160]
        if not slug:
            return None
        stmt = select(Topic).where(Topic.subject_code == subject_code, Topic.slug == slug)
        existing = self._db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing
        topic = Topic(
            subject_code=subject_code,
            exam_config_id=exam_config_id,
            name=cleaned[:160],
            slug=slug,
            is_canonical=False,
        )
        self._db.add(topic)
        self._db.flush()
        return topic

    def get_existing_stem_hashes(self, document_id: UUID) -> set[str]:
        """Return all existing `stem_hash` values for a document."""
        stmt = select(Question.stem_hash).where(Question.document_id == document_id)
        return set(self._db.execute(stmt).scalars().all())

    def list_existing_stems_for_user(
        self,
        user_id: UUID,
        *,
        subject_code: str | None = None,
    ) -> list[tuple[UUID, str, str]]:
        """Return `(id, stem_hash, question_text)` for all user-owned questions."""
        conditions = [self._user_ownership_condition(user_id)]
        if subject_code:
            conditions.append(Question.subject_code == subject_code)
        stmt = (
            select(Question.id, Question.stem_hash, Question.question_text, Question.document_id, Question.correct_answer_data)  # noqa: E501
            .outerjoin(Document, Document.id == Question.document_id)
            .where(*conditions)
        )
        rows: list[tuple[UUID, str, str]] = []
        for q_id, stem_hash, question_text, doc_id, answer_data in self._db.execute(stmt).all():
            if doc_id is None and not self._is_standalone_owned(q_id, answer_data, user_id):
                continue
            rows.append((q_id, stem_hash, question_text))
        return rows

    def _user_ownership_condition(self, user_id: UUID):
        user_test_question_ids = (
            select(TestQuestion.question_id)
            .join(Test, Test.id == TestQuestion.test_id)
            .where(Test.user_id == user_id, TestQuestion.question_id.is_not(None))
        )
        return or_(
            (Document.user_id == user_id) & (Document.deleted_at.is_(None)),
            (Question.document_id.is_(None))
            & or_(
                Question.id.in_(user_test_question_ids),
                cast(Question.correct_answer_data, String).contains(str(user_id)),
            ),
        )

    def _is_standalone_owned(
        self,
        question_id: UUID,
        answer_data: dict | None,
        user_id: UUID,
    ) -> bool:
        if isinstance(answer_data, dict) and answer_data.get("owner_user_id") == str(user_id):
            return True
        stmt = (
            select(TestQuestion.id)
            .join(Test, Test.id == TestQuestion.test_id)
            .where(TestQuestion.question_id == question_id, Test.user_id == user_id)
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none() is not None

    def get_question_with_options(
        self, question_id: UUID
    ) -> tuple[Question, str | None, list[QuestionOption]] | None:
        """Fetch a Question, its Topic name, and ordered QuestionOptions."""
        stmt = (
            select(Question, Topic.name)
            .outerjoin(Topic, Topic.id == Question.topic_id)
            .where(Question.id == question_id)
        )
        row = self._db.execute(stmt).first()
        if row is None:
            return None
        question, topic_name = row[0], row[1]
        opt_stmt = (
            select(QuestionOption)
            .where(QuestionOption.question_id == question.id)
            .order_by(QuestionOption.display_order.asc(), QuestionOption.option_key.asc())
        )
        options = list(self._db.execute(opt_stmt).scalars().all())
        return question, topic_name, options

    def is_owned_by_user(self, question: Question, user_id: UUID) -> bool:
        """Return True if `question` belongs to `user_id`."""
        if question.document_id is not None:
            doc = self._db.get(Document, question.document_id)
            return doc is not None and doc.deleted_at is None and doc.user_id == user_id
        return self._is_standalone_owned(question.id, question.correct_answer_data, user_id)

    def create_question_with_options(
        self,
        question: Question,
        options: list[QuestionOption],
    ) -> Question:
        """Stage a Question and its QuestionOptions in the current session."""
        self._db.add(question)
        self._db.flush()
        for option in options:
            option.question_id = question.id
            self._db.add(option)
        self._db.flush()
        return question

    def replace_options(
        self, question_id: UUID, options: list[QuestionOption]
    ) -> list[QuestionOption]:
        """Replace all options on an existing question."""
        self._db.execute(delete(QuestionOption).where(QuestionOption.question_id == question_id))
        self._db.flush()
        for option in options:
            option.question_id = question_id
            self._db.add(option)
        self._db.flush()
        return options

    def delete_question(self, question: Question) -> None:
        """Delete a Question row, nullifying TestQuestion FKs and removing options explicitly."""
        self._db.execute(
            update(TestQuestion)
            .where(TestQuestion.question_id == question.id)
            .values(question_id=None)
        )
        self._db.execute(delete(QuestionOption).where(QuestionOption.question_id == question.id))
        self._db.delete(question)
        self._db.commit()

    def record_ai_run(self, run: AIGenerationRun) -> AIGenerationRun:
        """Persist an AIGenerationRun audit entry."""
        self._db.add(run)
        self._db.flush()
        return run

    def load_knowledge_for_generation(
        self,
        user_id: UUID,
        *,
        document_id: UUID | None = None,
        topic_id: UUID | None = None,
        concept_id: UUID | None = None,
        subject_code: str | None = None,
    ) -> tuple[list[Concept], list[Fact], dict[UUID, Topic]]:
        """Load user-owned validated Concepts, Facts, and Topics for MCQ generation."""
        concept_conds = [Document.user_id == user_id, Document.deleted_at.is_(None)]
        fact_conds = [Document.user_id == user_id, Document.deleted_at.is_(None)]

        if document_id is not None:
            concept_conds.append(Concept.document_id == document_id)
            fact_conds.append(Fact.document_id == document_id)
        if topic_id is not None:
            concept_conds.append(Concept.topic_id == topic_id)
            fact_conds.append(Fact.topic_id == topic_id)
        if concept_id is not None:
            concept_conds.append(Concept.id == concept_id)

        concepts = list(
            self._db.execute(
                select(Concept)
                .join(Document, Document.id == Concept.document_id)
                .where(*concept_conds)
                .order_by(Concept.created_at.desc())
                .limit(20)
            )
            .scalars()
            .all()
        )

        # When filtering by a single concept_id, also pull facts from the same document/topic.
        if concept_id is not None and concepts and topic_id is None and concepts[0].topic_id:
            fact_conds.append(Fact.topic_id == concepts[0].topic_id)

        facts = list(
            self._db.execute(
                select(Fact)
                .join(Document, Document.id == Fact.document_id)
                .where(*fact_conds, Fact.review_status != "conflict")
                .order_by(Fact.created_at.desc())
                .limit(30)
            )
            .scalars()
            .all()
        )

        topic_ids = {
            t_id
            for t_id in ([c.topic_id for c in concepts] + [f.topic_id for f in facts] + [topic_id])
            if t_id is not None
        }
        topics_by_id: dict[UUID, Topic] = {}
        if topic_ids:
            for t in self._db.execute(select(Topic).where(Topic.id.in_(topic_ids))).scalars().all():
                topics_by_id[t.id] = t

        if subject_code:
            concepts = [
                c
                for c in concepts
                if c.topic_id is None
                or topics_by_id.get(c.topic_id) is None
                or topics_by_id[c.topic_id].subject_code == subject_code
            ]
            facts = [
                f
                for f in facts
                if f.topic_id is None
                or topics_by_id.get(f.topic_id) is None
                or topics_by_id[f.topic_id].subject_code == subject_code
            ]

        return concepts, facts, topics_by_id

    def commit(self) -> None:
        """Commit staged changes."""
        self._db.commit()

    def list_questions_for_user(
        self,
        user_id: UUID,
        *,
        document_id: UUID | None = None,
        subject_code: str | None = None,
        topic_id: UUID | None = None,
        difficulty: str | None = None,
        origin: str | None = None,
        validation_status: str | None = None,
        pyq_year: int | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[Question, str | None]], dict[UUID, list[QuestionOption]], int]:
        """Return filtered questions owned by `user_id`, their options, and total count."""
        conditions = [self._user_ownership_condition(user_id)]

        if document_id is not None:
            conditions.append(Question.document_id == document_id)
        if subject_code:
            conditions.append(Question.subject_code == subject_code)
        if topic_id is not None:
            conditions.append(Question.topic_id == topic_id)
        if difficulty:
            conditions.append(Question.difficulty == difficulty)
        if origin:
            conditions.append(Question.origin == origin)
        if validation_status:
            conditions.append(Question.validation_status == validation_status)
        if q:
            pattern = f"%{q.strip()}%"
            conditions.append(
                or_(
                    Question.question_text.ilike(pattern),
                    Question.supporting_excerpt.ilike(pattern),
                )
            )

        rows_stmt = (
            select(Question, Topic.name)
            .outerjoin(Document, Document.id == Question.document_id)
            .outerjoin(Topic, Topic.id == Question.topic_id)
            .where(*conditions)
            .order_by(
                Question.source_page_number.asc().nulls_last(),
                Question.created_at.desc(),
            )
        )
        all_rows = [(row[0], row[1]) for row in self._db.execute(rows_stmt).all()]

        # Verify standalone ownership & optional pyq_year filter in dialect-agnostic Python
        filtered_rows: list[tuple[Question, str | None]] = []
        for question, topic_name in all_rows:
            if question.document_id is None and not self._is_standalone_owned(
                question.id, question.correct_answer_data, user_id
            ):
                continue
            if pyq_year is not None:
                meta = question.pyq_metadata_json or {}
                raw_year = meta.get("year")
                try:
                    if raw_year is None or int(raw_year) != pyq_year:
                        continue
                except (TypeError, ValueError):
                    continue
            filtered_rows.append((question, topic_name))

        total = len(filtered_rows)
        paged_rows = filtered_rows[offset : offset + limit]

        options_by_question: dict[UUID, list[QuestionOption]] = {}
        if paged_rows:
            question_ids = [question.id for question, _ in paged_rows]
            opt_stmt = (
                select(QuestionOption)
                .where(QuestionOption.question_id.in_(question_ids))
                .order_by(QuestionOption.display_order.asc(), QuestionOption.option_key.asc())
            )
            for opt in self._db.execute(opt_stmt).scalars().all():
                options_by_question.setdefault(opt.question_id, []).append(opt)

        return paged_rows, options_by_question, total
