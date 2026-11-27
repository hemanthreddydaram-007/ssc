from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.assessment import Question
from app.models.document import Document, DocumentChunk, DocumentPage
from app.models.learning import AIGenerationRun, Concept, Fact, Topic
from app.schemas.topics import TopicSummaryOut


class KnowledgeRepository:
    """Data-access layer for topics, concepts, facts, and AI generation runs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_document_pages(self, document_id: UUID) -> list[DocumentPage]:
        return list(
            self.db.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            )
            .scalars()
            .all()
        )

    def get_document_chunks(self, document_id: UUID) -> list[DocumentChunk]:
        return list(
            self.db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
            .scalars()
            .all()
        )

    def get_topic_by_subject_slug(self, subject_code: str, slug: str) -> Topic | None:
        return self.db.execute(
            select(Topic).where(Topic.subject_code == subject_code, Topic.slug == slug)
        ).scalar_one_or_none()

    def list_topics_for_subject(self, subject_code: str) -> list[Topic]:
        return list(
            self.db.execute(
                select(Topic)
                .where(Topic.subject_code == subject_code)
                .order_by(Topic.sort_order, Topic.name)
            )
            .scalars()
            .all()
        )

    def get_or_create_topic(
        self,
        *,
        subject_code: str,
        name: str,
        slug: str,
        exam_config_id: UUID | None = None,
        is_canonical: bool = False,
        sort_order: int = 0,
    ) -> Topic:
        existing = self.get_topic_by_subject_slug(subject_code, slug)
        if existing is not None:
            return existing
        topic = Topic(
            subject_code=subject_code,
            exam_config_id=exam_config_id,
            name=name[:160],
            slug=slug[:160],
            is_canonical=is_canonical,
            sort_order=sort_order,
        )
        self.db.add(topic)
        self.db.flush()
        return topic

    def clear_document_knowledge(self, document_id: UUID) -> None:
        """Delete derived facts and concepts for a document when force-reprocessing."""
        self.db.execute(delete(Fact).where(Fact.document_id == document_id))
        self.db.execute(delete(Concept).where(Concept.document_id == document_id))
        self.db.flush()

    def list_facts_for_document(self, document_id: UUID) -> list[Fact]:
        return list(
            self.db.execute(
                select(Fact)
                .where(Fact.document_id == document_id)
                .order_by(Fact.source_page_number, Fact.created_at)
            )
            .scalars()
            .all()
        )

    def list_concepts_for_document(self, document_id: UUID) -> list[Concept]:
        return list(
            self.db.execute(
                select(Concept)
                .where(Concept.document_id == document_id)
                .order_by(Concept.created_at)
            )
            .scalars()
            .all()
        )

    def get_fact_with_owner(self, fact_id: UUID) -> tuple[Fact, Document] | None:
        row = self.db.execute(
            select(Fact, Document)
            .join(Document, Fact.document_id == Document.id)
            .where(Fact.id == fact_id, Document.deleted_at.is_(None))
        ).first()
        if row is None:
            return None
        return row[0], row[1]

    def find_fact_by_canonical_hash(
        self, document_id: UUID, canonical_hash: str
    ) -> Fact | None:
        return self.db.execute(
            select(Fact)
            .where(Fact.document_id == document_id, Fact.canonical_hash == canonical_hash)
            .limit(1)
        ).scalar_one_or_none()

    def find_facts_by_type_scope(
        self, document_id: UUID, topic_id: UUID | None, fact_type: str
    ) -> list[Fact]:
        stmt = select(Fact).where(
            Fact.document_id == document_id,
            Fact.fact_type == fact_type,
        )
        if topic_id is None:
            stmt = stmt.where(Fact.topic_id.is_(None))
        else:
            stmt = stmt.where(Fact.topic_id == topic_id)
        return list(self.db.execute(stmt).scalars().all())

    def find_concept_by_canonical_hash(
        self, document_id: UUID, canonical_hash: str
    ) -> Concept | None:
        return self.db.execute(
            select(Concept)
            .where(Concept.document_id == document_id, Concept.canonical_hash == canonical_hash)
            .limit(1)
        ).scalar_one_or_none()

    def list_topics_for_document(self, document_id: UUID) -> list[TopicSummaryOut]:
        facts = self.list_facts_for_document(document_id)
        concepts = self.list_concepts_for_document(document_id)
        q_rows = self.db.execute(
            select(Question.topic_id, func.count())
            .where(Question.document_id == document_id, Question.topic_id.is_not(None))
            .group_by(Question.topic_id)
        ).all()
        q_counts: dict[UUID, int] = {row[0]: int(row[1]) for row in q_rows if row[0] is not None}

        topic_ids: set[UUID] = set()
        fact_counts: dict[UUID, int] = {}
        concept_counts: dict[UUID, int] = {}
        pages_by_topic: dict[UUID, set[int]] = {}

        for f in facts:
            if f.topic_id is not None:
                topic_ids.add(f.topic_id)
                fact_counts[f.topic_id] = fact_counts.get(f.topic_id, 0) + 1
                if f.source_page_number is not None:
                    pages_by_topic.setdefault(f.topic_id, set()).add(f.source_page_number)

        for c in concepts:
            if c.topic_id is not None:
                topic_ids.add(c.topic_id)
                concept_counts[c.topic_id] = concept_counts.get(c.topic_id, 0) + 1
                for ref in c.source_refs_json or []:
                    if isinstance(ref, dict) and isinstance(ref.get("page_number"), int):
                        pages_by_topic.setdefault(c.topic_id, set()).add(ref["page_number"])

        topic_ids.update(q_counts.keys())
        if not topic_ids:
            return []

        topics = list(
            self.db.execute(
                select(Topic)
                .where(Topic.id.in_(topic_ids))
                .order_by(Topic.subject_code, Topic.sort_order, Topic.name)
            )
            .scalars()
            .all()
        )
        return [
            TopicSummaryOut(
                id=t.id,
                subject_code=t.subject_code,
                exam_config_id=t.exam_config_id,
                parent_topic_id=t.parent_topic_id,
                name=t.name,
                slug=t.slug,
                description=t.description,
                is_canonical=t.is_canonical,
                sort_order=t.sort_order,
                concept_count=concept_counts.get(t.id, 0),
                fact_count=fact_counts.get(t.id, 0),
                question_count=q_counts.get(t.id, 0),
                source_pages=sorted(pages_by_topic.get(t.id, set())),
            )
            for t in topics
        ]

    def list_topics_for_user(
        self,
        user_id: UUID,
        *,
        subject_code: str | None = None,
    ) -> list[TopicSummaryOut]:
        """List topics linked to a user's active documents (plus canonical topics for filter)."""
        user_doc_ids = select(Document.id).where(
            Document.user_id == user_id, Document.deleted_at.is_(None)
        )

        fact_rows = self.db.execute(
            select(Fact.topic_id, func.count())
            .where(Fact.document_id.in_(user_doc_ids), Fact.topic_id.is_not(None))
            .group_by(Fact.topic_id)
        ).all()
        concept_rows = self.db.execute(
            select(Concept.topic_id, func.count())
            .where(Concept.document_id.in_(user_doc_ids), Concept.topic_id.is_not(None))
            .group_by(Concept.topic_id)
        ).all()
        q_rows = self.db.execute(
            select(Question.topic_id, func.count())
            .where(Question.document_id.in_(user_doc_ids), Question.topic_id.is_not(None))
            .group_by(Question.topic_id)
        ).all()

        fact_counts = {r[0]: int(r[1]) for r in fact_rows if r[0] is not None}
        concept_counts = {r[0]: int(r[1]) for r in concept_rows if r[0] is not None}
        q_counts = {r[0]: int(r[1]) for r in q_rows if r[0] is not None}

        used_ids = set(fact_counts) | set(concept_counts) | set(q_counts)
        stmt = select(Topic)
        if subject_code:
            stmt = stmt.where(Topic.subject_code == subject_code)
        if used_ids:
            stmt = stmt.where((Topic.id.in_(used_ids)) | (Topic.is_canonical == True))  # noqa: E712
        else:
            stmt = stmt.where(Topic.is_canonical == True)  # noqa: E712

        topics = list(
            self.db.execute(stmt.order_by(Topic.subject_code, Topic.sort_order, Topic.name))
            .scalars()
            .all()
        )
        return [
            TopicSummaryOut(
                id=t.id,
                subject_code=t.subject_code,
                exam_config_id=t.exam_config_id,
                parent_topic_id=t.parent_topic_id,
                name=t.name,
                slug=t.slug,
                description=t.description,
                is_canonical=t.is_canonical,
                sort_order=t.sort_order,
                concept_count=concept_counts.get(t.id, 0),
                fact_count=fact_counts.get(t.id, 0),
                question_count=q_counts.get(t.id, 0),
                source_pages=[],
            )
            for t in topics
        ]

    def record_generation_run(self, run: AIGenerationRun) -> AIGenerationRun:
        self.db.add(run)
        self.db.flush()
        return run
