from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.ai.prompts.extraction import KNOWLEDGE_EXTRACTION_PROMPT_V1
from app.ai.provider import AIConfigurationError, AIProviderError, LLMProvider
from app.ai.schemas.extraction import ChunkExtractionOutput
from app.db.base import utcnow
from app.models.document import Document, ProcessingJob
from app.models.learning import AIGenerationRun
from app.repositories.knowledge_repo import KnowledgeRepository
from app.schemas.knowledge import CandidateOption, ExtractedQuestionCandidate
from app.services.classification.classifier import DocumentClassifier
from app.services.classification.topic_mapper import CANONICAL_TOPICS, TopicMapper
from app.services.extraction.coverage_audit import build_coverage_audit
from app.services.knowledge.deduplicator import upsert_concept, upsert_fact
from app.services.knowledge.grounding import format_chunk_with_page_markers, verify_grounding

logger = logging.getLogger(__name__)


class MissingExtractionContentError(Exception):
    """Raised when knowledge extraction is requested before pages/chunks exist."""


def _make_knowledge_stages() -> list[dict[str, Any]]:
    return [
        {
            "name": "classification",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
        {
            "name": "knowledge_extraction",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
        {
            "name": "grounding_dedup",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
        {
            "name": "question_ingestion",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
    ]


class KnowledgeExtractionPipeline:
    """Orchestrates document classification, chunk knowledge extraction, grounding, and dedup."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    @staticmethod
    def _set_stage(stages: list[dict[str, Any]], name: str, **updates: Any) -> None:
        for stage in stages:
            if stage["name"] == name:
                stage.update(updates)
                return

    @staticmethod
    def _assign_stages(job: ProcessingJob, stages: list[dict[str, Any]]) -> None:
        job.stage_details_json = deepcopy(stages)
        flag_modified(job, "stage_details_json")

    def _update_job(
        self,
        db: Session,
        job: ProcessingJob,
        *,
        status: str | None = None,
        stage: str | None = None,
        stages: list[dict[str, Any]] | None = None,
        processed_items: int | None = None,
        total_items: int | None = None,
    ) -> None:
        if status is not None:
            job.status = status
            if status == "running" and job.started_at is None:
                job.started_at = utcnow()
        if stage is not None:
            job.current_stage = stage
        if stages is not None:
            self._assign_stages(job, stages)
        if total_items is not None:
            job.total_items = total_items
        if processed_items is not None:
            job.processed_items = processed_items
        if job.total_items and job.total_items > 0:
            job.progress_percent = int(min(100, round(job.processed_items * 100 / job.total_items)))
        else:
            job.progress_percent = None
        db.add(job)
        db.commit()

    def _fail_job(
        self,
        db: Session,
        job: ProcessingJob,
        error_code: str,
        error_message: str,
        stages: list[dict[str, Any]],
    ) -> None:
        job.status = "failed"
        job.error_code = error_code
        job.error_message = error_message
        job.finished_at = utcnow()
        self._assign_stages(job, stages)
        db.add(job)
        db.commit()

    def run(
        self,
        db: Session,
        document: Document,
        job: ProcessingJob,
        *,
        force_reprocess: bool = False,
    ) -> None:
        repo = KnowledgeRepository(db)
        pages = repo.get_document_pages(document.id)
        chunks = repo.get_document_chunks(document.id)

        stages = _make_knowledge_stages()
        if not pages or not chunks:
            self._set_stage(
                stages,
                "classification",
                status="failed",
                error_code="EXTRACTION_REQUIRED",
                error_message="Document has no extracted pages or chunks yet.",
            )
            self._fail_job(
                db,
                job,
                "EXTRACTION_REQUIRED",
                "Document has no extracted pages or chunks yet.",
                stages,
            )
            return

        total_chunks = len(chunks)
        self._set_stage(
            stages, "classification", status="running", processed_items=0, total_items=1
        )
        self._update_job(
            db,
            job,
            status="running",
            stage="classification",
            stages=stages,
            processed_items=0,
            total_items=total_chunks,
        )

        if force_reprocess:
            repo.clear_document_knowledge(document.id)
            db.commit()

        pages_by_num = {p.page_number: p.extracted_text for p in pages}

        try:
            classifier = DocumentClassifier(db, self.llm_provider)
            classification = classifier.classify_document(
                document,
                pages=pages,
                chunks=chunks,
                job_id=job.id,
            )
            db.commit()
        except AIConfigurationError as exc:
            self._set_stage(
                stages,
                "classification",
                status="failed",
                error_code="AI_CONFIG_ERROR",
                error_message=str(exc),
            )
            self._fail_job(db, job, "AI_CONFIG_ERROR", str(exc), stages)
            return
        except AIProviderError as exc:
            self._set_stage(
                stages,
                "classification",
                status="failed",
                error_code="AI_PROVIDER_ERROR",
                error_message=str(exc),
            )
            self._fail_job(db, job, "AI_PROVIDER_ERROR", str(exc), stages)
            return

        self._set_stage(
            stages, "classification", status="completed", processed_items=1, total_items=1
        )
        self._set_stage(
            stages,
            "knowledge_extraction",
            status="running",
            processed_items=0,
            total_items=total_chunks,
        )
        self._update_job(
            db,
            job,
            stage="knowledge_extraction",
            stages=stages,
            processed_items=0,
            total_items=total_chunks,
        )

        topic_mapper = TopicMapper(db, exam_config_id=document.exam_config_id)
        topic_id_map: dict[str, UUID] = {}
        question_candidates: list[ExtractedQuestionCandidate] = []
        failed_chunks = 0
        grounded_records = 0

        for idx, chunk in enumerate(chunks, start=1):
            effective_subject = classification.effective_subject_code or "unknown"
            topic_hints = ", ".join(CANONICAL_TOPICS.get(effective_subject, ())) or "none"
            chunk_text = format_chunk_with_page_markers(chunk, pages_by_num)
            prompt = KNOWLEDGE_EXTRACTION_PROMPT_V1.render(
                subject_code=effective_subject,
                exam_code="ssc_chsl_tier_1",
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_title=chunk.section_title or "none",
                topic_hints=topic_hints,
                chunk_text=chunk_text,
            )

            try:
                result = self.llm_provider.generate_structured_output(
                    ChunkExtractionOutput,
                    prompt,
                    system_instruction=KNOWLEDGE_EXTRACTION_PROMPT_V1.system_instruction,
                    model_tier="standard",
                    temperature=0.1,
                    prompt_name=KNOWLEDGE_EXTRACTION_PROMPT_V1.name,
                    prompt_version=KNOWLEDGE_EXTRACTION_PROMPT_V1.version,
                )
            except (AIConfigurationError, AIProviderError) as exc:
                code = (
                    "AI_CONFIG_ERROR"
                    if isinstance(exc, AIConfigurationError)
                    else "AI_PROVIDER_ERROR"
                )
                self._set_stage(
                    stages,
                    "knowledge_extraction",
                    status="failed",
                    processed_items=idx - 1,
                    total_items=total_chunks,
                    error_code=code,
                    error_message=str(exc),
                )
                self._fail_job(db, job, code, str(exc), stages)
                return

            run = AIGenerationRun(
                document_id=document.id,
                job_id=job.id,
                stage="knowledge_extraction",
                model_name=result.model_name,
                prompt_name=result.prompt_name,
                prompt_version=result.prompt_version,
                latency_ms=result.latency_ms,
                token_usage_json=result.token_usage,
                validation_status=result.status,
                error_message=result.error_message,
            )
            repo.record_generation_run(run)

            if result.parsed is None or result.status == "failed_validation":
                failed_chunks += 1
                db.commit()
                self._set_stage(
                    stages,
                    "knowledge_extraction",
                    status="running",
                    processed_items=idx,
                    total_items=total_chunks,
                )
                self._update_job(
                    db,
                    job,
                    stage="knowledge_extraction",
                    stages=stages,
                    processed_items=idx,
                    total_items=total_chunks,
                )
                continue

            parsed = result.parsed
            chunk_subject = (
                effective_subject
                if effective_subject != "unknown"
                else parsed.detected_subject_code
            )

            for fact_item in parsed.facts:
                topic = topic_mapper.map_topic(
                    subject_code=chunk_subject,
                    topic_name=fact_item.topic_name,
                )
                if topic is not None and fact_item.topic_name:
                    topic_id_map[fact_item.topic_name] = topic.id
                    topic_id_map[topic.name] = topic.id

                grounding = verify_grounding(
                    pages_by_num,
                    claimed_page=fact_item.source_page_number,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    supporting_excerpt=fact_item.supporting_excerpt,
                    claimed_provenance=fact_item.provenance,
                    confidence=fact_item.confidence,
                )
                upsert_fact(
                    repo,
                    document_id=document.id,
                    topic_id=topic.id if topic else None,
                    chunk_id=chunk.id,
                    fact_type=fact_item.fact_type,
                    content=fact_item.content,
                    provenance=grounding.provenance,
                    confidence=fact_item.confidence,
                    source_page_number=grounding.resolved_page_number,
                    supporting_excerpt=grounding.supporting_excerpt,
                    is_time_sensitive=fact_item.is_time_sensitive,
                    source_date_label=fact_item.source_date_label,
                    review_status=grounding.review_status,
                    model_name=result.model_name,
                    prompt_name=result.prompt_name,
                    prompt_version=result.prompt_version,
                    generation_run_id=run.id,
                )
                grounded_records += 1

            for concept_item in parsed.concepts:
                topic = topic_mapper.map_topic(
                    subject_code=chunk_subject,
                    topic_name=concept_item.topic_name,
                )
                if topic is not None and concept_item.topic_name:
                    topic_id_map[concept_item.topic_name] = topic.id
                    topic_id_map[topic.name] = topic.id

                grounding = verify_grounding(
                    pages_by_num,
                    claimed_page=concept_item.source_page_number,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    supporting_excerpt=concept_item.supporting_excerpt,
                    claimed_provenance=concept_item.provenance,
                    confidence=concept_item.confidence,
                )
                upsert_concept(
                    repo,
                    document_id=document.id,
                    topic_id=topic.id if topic else None,
                    title=concept_item.title,
                    explanation=concept_item.explanation,
                    difficulty=concept_item.difficulty,
                    provenance=grounding.provenance,
                    confidence=concept_item.confidence,
                    review_status=grounding.review_status,
                    source_page_number=grounding.resolved_page_number,
                    chunk_id=chunk.id,
                    supporting_excerpt=grounding.supporting_excerpt,
                    prerequisites=concept_item.prerequisites,
                    related_concepts=concept_item.related_concepts,
                    model_name=result.model_name,
                    prompt_name=result.prompt_name,
                    prompt_version=result.prompt_version,
                    generation_run_id=run.id,
                )
                grounded_records += 1

            for q_item in parsed.questions:
                q_subject = (
                    q_item.subject_code if q_item.subject_code != "unknown" else chunk_subject
                )
                if q_item.topic_name and q_item.topic_name not in topic_id_map:
                    q_topic = topic_mapper.map_topic(
                        subject_code=q_subject,
                        topic_name=q_item.topic_name,
                    )
                    if q_topic is not None:
                        topic_id_map[q_item.topic_name] = q_topic.id
                        topic_id_map[q_topic.name] = q_topic.id

                q_grounding = verify_grounding(
                    pages_by_num,
                    claimed_page=q_item.source_page_number,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    supporting_excerpt=q_item.supporting_excerpt or q_item.question_text[:180],
                    claimed_provenance="extracted",
                    confidence=0.85,
                )
                question_candidates.append(
                    ExtractedQuestionCandidate(
                        question_text=q_item.question_text,
                        question_type=q_item.question_type,
                        subject_code=q_subject,
                        topic_name=q_item.topic_name,
                        difficulty=q_item.difficulty,
                        options=[
                            CandidateOption(key=opt.key, text=opt.text) for opt in q_item.options
                        ],
                        correct_option_key=q_item.correct_option_key,
                        explanation=q_item.explanation,
                        source_page_number=q_grounding.resolved_page_number,
                        supporting_excerpt=q_grounding.supporting_excerpt,
                        answer_key_provenance=q_item.answer_key_provenance,
                        pyq_metadata=(
                            q_item.pyq_metadata.model_dump(exclude_none=True)
                            if q_item.pyq_metadata is not None
                            else None
                        ),
                        passage_text=q_item.passage_text,
                        model_name=result.model_name,
                        prompt_name=result.prompt_name,
                        prompt_version=result.prompt_version,
                    )
                )

            db.commit()
            self._set_stage(
                stages,
                "knowledge_extraction",
                status="running",
                processed_items=idx,
                total_items=total_chunks,
            )
            self._update_job(
                db,
                job,
                stage="knowledge_extraction",
                stages=stages,
                processed_items=idx,
                total_items=total_chunks,
            )

        self._set_stage(
            stages,
            "knowledge_extraction",
            status="completed",
            processed_items=total_chunks,
            total_items=total_chunks,
            error_message=(
                f"{failed_chunks} chunk(s) failed schema validation and were skipped."
                if failed_chunks
                else None
            ),
        )
        self._set_stage(
            stages,
            "grounding_dedup",
            status="completed",
            processed_items=grounded_records,
            total_items=grounded_records,
        )

        # Stage 4: Question candidate handoff to @assessment-engineer
        self._set_stage(
            stages,
            "question_ingestion",
            status="running",
            processed_items=0,
            total_items=len(question_candidates),
        )
        self._update_job(db, job, stage="question_ingestion", stages=stages)

        if question_candidates:
            try:
                from app.services.question_generation.ingestion import (  # noqa: PLC0415
                    QuestionIngestionService,
                )

                ingestion_svc = QuestionIngestionService(db)
                summary = ingestion_svc.ingest_candidates(
                    document_id=document.id,
                    candidates=question_candidates,
                    topic_id_map=topic_id_map,
                )
                ingested_count = getattr(summary, "inserted_count", len(question_candidates))
                self._set_stage(
                    stages,
                    "question_ingestion",
                    status="completed",
                    processed_items=ingested_count,
                    total_items=len(question_candidates),
                )
            except ImportError:
                logger.warning("QuestionIngestionService unavailable; skipping question handoff.")
                self._set_stage(
                    stages,
                    "question_ingestion",
                    status="skipped",
                    processed_items=0,
                    total_items=len(question_candidates),
                )
        else:
            self._set_stage(
                stages,
                "question_ingestion",
                status="completed",
                processed_items=0,
                total_items=0,
            )

        audit = build_coverage_audit(db, document.id)
        document.coverage_summary_json = audit.model_dump(mode="json")
        document.status = "knowledge_ready"
        db.add(document)

        job.status = "completed"
        job.current_stage = "completed"
        job.finished_at = utcnow()
        job.processed_items = total_chunks
        job.total_items = total_chunks
        job.progress_percent = 100
        self._assign_stages(job, stages)
        db.add(job)
        db.commit()


def run_knowledge_extraction_in_session(
    *,
    session_factory: sessionmaker[Session],
    document_id: UUID,
    job_id: UUID,
    llm_provider: LLMProvider,
    force_reprocess: bool = False,
) -> None:
    """BackgroundTask entry point opening an isolated SQLAlchemy session."""
    db = session_factory()
    try:
        document = db.get(Document, document_id)
        job = db.get(ProcessingJob, job_id)
        if document is None or job is None:
            logger.warning(
                "Knowledge extraction aborted: missing document=%s or job=%s",
                document_id,
                job_id,
            )
            return
        pipeline = KnowledgeExtractionPipeline(llm_provider=llm_provider)
        pipeline.run(db, document, job, force_reprocess=force_reprocess)
    except Exception as exc:
        logger.exception("Unhandled error during knowledge extraction for document %s", document_id)
        job = db.get(ProcessingJob, job_id)
        if job is not None and job.status not in ("completed", "failed"):
            job.status = "failed"
            job.error_code = "KNOWLEDGE_EXTRACTION_ERROR"
            job.error_message = str(exc)
            job.finished_at = utcnow()
            db.add(job)
            db.commit()
    finally:
        db.close()
