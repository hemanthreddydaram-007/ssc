from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.assessment import Question, TestQuestion
from app.models.document import (
    Document,
    DocumentAsset,
    DocumentChunk,
    DocumentPage,
    ProcessingJob,
)
from app.models.learning import AIGenerationRun, Concept, Fact, Note
from app.models.user import ExamConfig


class DocumentRepository:
    """Data-access layer for documents and related storage/extraction records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def exam_config_exists(self, exam_config_id: UUID) -> bool:
        """Return True if the referenced exam config exists."""
        stmt = select(ExamConfig.id).where(ExamConfig.id == exam_config_id)
        return self.db.execute(stmt).scalar_one_or_none() is not None

    def find_active_by_sha256(self, user_id: UUID, sha256: str) -> Document | None:
        """Find an active (non-deleted) document matching user and SHA-256 hash."""
        stmt = (
            select(Document)
            .where(
                Document.user_id == user_id,
                Document.sha256 == sha256,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, document_id: UUID, *, include_deleted: bool = False) -> Document | None:
        """Fetch a document by ID."""
        stmt = select(Document).where(Document.id == document_id)
        if not include_deleted:
            stmt = stmt.where(Document.deleted_at.is_(None))
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, document: Document) -> Document:
        """Persist a new Document record."""
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def save(self, document: Document) -> Document:
        """Commit updates to an existing Document record."""
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def list_for_user(
        self,
        user_id: UUID,
        *,
        subject_code: str | None = None,
        material_type: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        """Return paginated active documents for a user and total matching count."""
        conditions = [Document.user_id == user_id, Document.deleted_at.is_(None)]

        if subject_code:
            conditions.append(
                or_(
                    Document.subject_code == subject_code,
                    and_(
                        Document.subject_code.is_(None),
                        Document.detected_subject_code == subject_code,
                    ),
                )
            )
        if material_type:
            conditions.append(Document.material_type == material_type)
        if status:
            conditions.append(Document.status == status)
        if q:
            pattern = f"%{q.strip()}%"
            conditions.append(
                or_(
                    Document.title.ilike(pattern),
                    Document.original_filename.ilike(pattern),
                    Document.chapter_or_topic_hint.ilike(pattern),
                    Document.source_label.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(Document).where(*conditions)
        total = int(self.db.execute(count_stmt).scalar_one())

        items_stmt = (
            select(Document)
            .where(*conditions)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(self.db.execute(items_stmt).scalars().all())
        return items, total

    def list_asset_storage_keys(self, document_id: UUID) -> list[str]:
        """Return all extracted asset storage keys associated with a document."""
        stmt = select(DocumentAsset.storage_key).where(DocumentAsset.document_id == document_id)
        return list(self.db.execute(stmt).scalars().all())

    def delete_document(
        self,
        document: Document,
        *,
        cascade_derived: bool = True,
        deleted_at: datetime | None = None,
    ) -> None:
        """Delete a document following the configured derived-record retention policy.

        When `cascade_derived=True`, derived notes/facts/concepts/chunks/pages/jobs/assets
        are deleted, questions referenced by `test_questions` have `document_id` set to NULL,
        unreferenced questions from this document are deleted, and the document row is removed.

        When `cascade_derived=False`, derived records are preserved and the document is
        soft-deleted (`deleted_at` set) since derived learning tables require a document FK.
        """
        doc_id = document.id

        if not cascade_derived:
            document.deleted_at = deleted_at or utcnow()
            document.status = "deleted"
            self.db.add(document)
            self.db.commit()
            return

        referenced_q_subq = select(TestQuestion.question_id).where(
            TestQuestion.question_id.is_not(None)
        )
        self.db.execute(
            update(Question)
            .where(Question.document_id == doc_id, Question.id.in_(referenced_q_subq))
            .values(document_id=None, diagram_asset_id=None)
        )
        self.db.execute(
            delete(Question).where(
                Question.document_id == doc_id, Question.id.not_in(referenced_q_subq)
            )
        )

        self.db.execute(delete(Note).where(Note.document_id == doc_id))
        self.db.execute(delete(Fact).where(Fact.document_id == doc_id))
        self.db.execute(delete(Concept).where(Concept.document_id == doc_id))
        self.db.execute(delete(AIGenerationRun).where(AIGenerationRun.document_id == doc_id))
        self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
        self.db.execute(delete(DocumentAsset).where(DocumentAsset.document_id == doc_id))
        self.db.execute(delete(DocumentPage).where(DocumentPage.document_id == doc_id))
        self.db.execute(delete(ProcessingJob).where(ProcessingJob.document_id == doc_id))

        self.db.delete(document)
        self.db.commit()
