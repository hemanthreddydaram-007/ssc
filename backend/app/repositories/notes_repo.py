from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.assessment import Question
from app.models.document import Document
from app.models.learning import Concept, Fact, Note, Topic


class NotesRepository:
    """Data-access layer for smart notes and note-generation source records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_note_with_owner(self, note_id: UUID) -> tuple[Note, Document, str | None] | None:
        row = self.db.execute(
            select(Note, Document, Topic.name)
            .join(Document, Note.document_id == Document.id)
            .outerjoin(Topic, Note.topic_id == Topic.id)
            .where(Note.id == note_id, Document.deleted_at.is_(None))
        ).first()
        if row is None:
            return None
        return row[0], row[1], row[2]

    def find_existing_note(
        self,
        *,
        document_id: UUID,
        topic_id: UUID | None,
        note_type: str,
    ) -> Note | None:
        stmt = select(Note).where(
            Note.document_id == document_id,
            Note.note_type == note_type,
        )
        if topic_id is None:
            stmt = stmt.where(Note.topic_id.is_(None))
        else:
            stmt = stmt.where(Note.topic_id == topic_id)
        return self.db.execute(stmt.order_by(Note.created_at.desc()).limit(1)).scalar_one_or_none()

    def list_notes(
        self,
        *,
        user_id: UUID,
        document_id: UUID | None = None,
        note_type: str | None = None,
        topic_id: UUID | None = None,
        subject_code: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[Note, str | None]], int]:
        conditions = [Document.user_id == user_id, Document.deleted_at.is_(None)]
        if document_id is not None:
            conditions.append(Note.document_id == document_id)
        if note_type:
            conditions.append(Note.note_type == note_type)
        if topic_id is not None:
            conditions.append(Note.topic_id == topic_id)
        if subject_code:
            conditions.append(Note.subject_code == subject_code)
        if status:
            conditions.append(Note.status == status)
        if q:
            pattern = f"%{q.strip()}%"
            conditions.append(or_(Note.title.ilike(pattern), Topic.name.ilike(pattern)))

        count_stmt = (
            select(func.count())
            .select_from(Note)
            .join(Document, Note.document_id == Document.id)
            .outerjoin(Topic, Note.topic_id == Topic.id)
            .where(*conditions)
        )
        total = int(self.db.execute(count_stmt).scalar_one())

        rows_stmt = (
            select(Note, Topic.name)
            .join(Document, Note.document_id == Document.id)
            .outerjoin(Topic, Note.topic_id == Topic.id)
            .where(*conditions)
            .order_by(Note.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = [(r[0], r[1]) for r in self.db.execute(rows_stmt).all()]
        return rows, total

    def get_document_knowledge_scope(
        self,
        *,
        document_id: UUID,
        topic_id: UUID | None,
    ) -> tuple[list[Concept], list[Fact], list[Question]]:
        """Load stored Concept, Fact, and Question records for a document/topic scope."""
        c_stmt = select(Concept).where(Concept.document_id == document_id)
        f_stmt = select(Fact).where(Fact.document_id == document_id)
        q_stmt = select(Question).where(Question.document_id == document_id)

        if topic_id is not None:
            c_stmt = c_stmt.where(Concept.topic_id == topic_id)
            f_stmt = f_stmt.where(Fact.topic_id == topic_id)
            q_stmt = q_stmt.where(Question.topic_id == topic_id)

        concepts = list(self.db.execute(c_stmt.order_by(Concept.created_at)).scalars().all())
        facts = list(self.db.execute(f_stmt.order_by(Fact.source_page_number)).scalars().all())
        questions = list(
            self.db.execute(q_stmt.order_by(Question.source_page_number)).scalars().all()
        )
        return concepts, facts, questions

    def list_document_topic_ids_with_knowledge(
        self, document_id: UUID
    ) -> list[UUID | None]:
        """Return distinct topic IDs ordered by knowledge density (concepts + facts desc)."""
        topic_scores: dict[UUID, int] = {}
        has_uncategorized = False

        for model in (Fact, Concept):
            rows = self.db.execute(
                select(model.topic_id, func.count())
                .where(model.document_id == document_id)
                .group_by(model.topic_id)
            ).all()
            for topic_id, count in rows:
                if topic_id is None:
                    has_uncategorized = True
                else:
                    topic_scores[topic_id] = topic_scores.get(topic_id, 0) + int(count or 0)

        # Prefer highest-signal named topics first; fall back to [None] if uncategorized only
        if topic_scores:
            named = sorted(
                topic_scores.keys(),
                key=lambda tid: (-topic_scores[tid], str(tid)),
            )
            return named + ([None] if has_uncategorized else [])
        return [None] if has_uncategorized else []

    def count_knowledge_records(self, document_id: UUID) -> int:
        f_count = int(
            self.db.execute(
                select(func.count()).select_from(Fact).where(Fact.document_id == document_id)
            ).scalar_one()
        )
        c_count = int(
            self.db.execute(
                select(func.count()).select_from(Concept).where(Concept.document_id == document_id)
            ).scalar_one()
        )
        return f_count + c_count
