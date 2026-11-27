from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.ai.prompts.notes import (
    DETAILED_NOTES_PROMPT_V1,
    FORMULA_SHEET_PROMPT_V1,
    QUICK_REVISION_PROMPT_V1,
)
from app.ai.prompts.strategies import STRATEGY_SHEET_PROMPT_V1
from app.ai.provider import AIConfigurationError, AIProviderError, LLMProvider
from app.ai.schemas.notes import GeneratedNoteOutput
from app.db.base import utcnow
from app.models.assessment import Question
from app.models.document import Document, ProcessingJob
from app.models.learning import AIGenerationRun, Concept, Fact, Note, Topic
from app.repositories.notes_repo import NotesRepository
from app.schemas.notes import NoteContentJson
from app.services.notes.validators import validate_generated_note
from app.services.subjects.registry import SUBJECT_ADAPTER_REGISTRY

logger = logging.getLogger(__name__)


def _make_note_stages() -> list[dict[str, Any]]:
    return [
        {
            "name": "load_knowledge",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
        {
            "name": "generate_notes",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
        {
            "name": "validate_notes",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
    ]


def serialize_knowledge_payload(
    *,
    concepts: list[Concept],
    facts: list[Fact],
    questions: list[Question],
) -> str:
    """Serialize stored DB knowledge records into JSON for grounded note prompts."""
    payload = {
        "concepts": [
            {
                "id": str(c.id),
                "title": c.title,
                "explanation": c.explanation,
                "difficulty": c.difficulty,
                "provenance": c.provenance,
                "source_refs": c.source_refs_json or [],
            }
            for c in concepts
        ],
        "facts": [
            {
                "id": str(f.id),
                "fact_type": f.fact_type,
                "content": f.content,
                "provenance": f.provenance,
                "source_page_number": f.source_page_number,
                "supporting_excerpt": f.supporting_excerpt,
                "is_time_sensitive": f.is_time_sensitive,
                "source_date_label": f.source_date_label,
                "review_status": f.review_status,
            }
            for f in facts
        ],
        "questions": [
            {
                "id": str(q.id),
                "question_text": q.question_text,
                "difficulty": q.difficulty,
                "source_page_number": q.source_page_number,
                "pyq_metadata": q.pyq_metadata_json,
            }
            for q in questions[:5]
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


def _insufficient_evidence_content(topic_name: str) -> dict[str, Any]:
    return NoteContentJson(
        summary=f"Not enough verified knowledge records for '{topic_name}'.",
        sections=[],
        insufficient_evidence_message=(
            f"Not enough information: no extracted concepts or facts exist for '{topic_name}' "
            "yet. Run knowledge extraction or upload relevant material for this topic."
        ),
    ).model_dump(mode="json")


class NoteGenerationPipeline:
    """Generates detailed, quick-revision, formula, and strategy notes from stored DB records."""

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

    @staticmethod
    def _ordered_note_types(note_types: list[str]) -> list[str]:
        priority = {"detailed": 0, "formula_sheet": 1, "strategy_sheet": 2, "quick_revision": 3}
        seen: list[str] = []
        for nt in sorted(note_types, key=lambda x: priority.get(x, 99)):
            if nt not in seen:
                seen.append(nt)
        return seen

    def run(
        self,
        db: Session,
        document: Document,
        job: ProcessingJob,
        *,
        note_types: list[str],
        topic_ids: list[UUID] | None = None,
        force_regenerate: bool = False,
    ) -> None:
        repo = NotesRepository(db)
        stages = _make_note_stages()

        self._set_stage(
            stages, "load_knowledge", status="running", processed_items=0, total_items=1
        )
        self._update_job(db, job, status="running", stage="load_knowledge", stages=stages)

        if repo.count_knowledge_records(document.id) == 0:
            self._set_stage(
                stages,
                "load_knowledge",
                status="failed",
                error_code="KNOWLEDGE_REQUIRED",
                error_message="No extracted facts or concepts exist for this document yet.",
            )
            self._fail_job(
                db,
                job,
                "KNOWLEDGE_REQUIRED",
                "No extracted facts or concepts exist for this document yet.",
                stages,
            )
            return

        target_topic_ids: list[UUID | None] = (
            list(topic_ids)
            if topic_ids is not None
            else repo.list_document_topic_ids_with_knowledge(document.id)
        )
        if not target_topic_ids:
            target_topic_ids = [None]

        ordered_types = self._ordered_note_types(note_types)
        total_targets = len(target_topic_ids) * len(ordered_types)

        self._set_stage(
            stages, "load_knowledge", status="completed", processed_items=1, total_items=1
        )
        self._set_stage(
            stages,
            "generate_notes",
            status="running",
            processed_items=0,
            total_items=total_targets,
        )
        self._update_job(
            db,
            job,
            stage="generate_notes",
            stages=stages,
            processed_items=0,
            total_items=total_targets,
        )

        done_count = 0
        validated_count = 0

        for topic_id in target_topic_ids:
            topic = db.get(Topic, topic_id) if topic_id is not None else None
            topic_name = topic.name if topic is not None else "General Document Notes"
            subject_code = (
                topic.subject_code
                if topic is not None and topic.subject_code
                else (document.subject_code or document.detected_subject_code or "unknown")
            )
            adapter = SUBJECT_ADAPTER_REGISTRY.get(subject_code)

            concepts, facts, questions = repo.get_document_knowledge_scope(
                document_id=document.id,
                topic_id=topic_id,
            )
            detailed_content: NoteContentJson | None = None

            for note_type in ordered_types:
                existing = repo.find_existing_note(
                    document_id=document.id,
                    topic_id=topic_id,
                    note_type=note_type,
                )
                if existing is not None and not force_regenerate:
                    if note_type == "detailed" and existing.content_json:
                        try:
                            detailed_content = NoteContentJson.model_validate(existing.content_json)
                        except Exception:
                            detailed_content = None
                    done_count += 1
                    self._set_stage(
                        stages,
                        "generate_notes",
                        status="running",
                        processed_items=done_count,
                        total_items=total_targets,
                    )
                    self._update_job(
                        db,
                        job,
                        stage="generate_notes",
                        stages=stages,
                        processed_items=done_count,
                        total_items=total_targets,
                    )
                    continue

                if not concepts and not facts:
                    note = existing or Note(
                        document_id=document.id,
                        topic_id=topic_id,
                        subject_code=subject_code,
                        note_type=note_type,
                        title=f"{topic_name} — {note_type.replace('_', ' ').title()}",
                    )
                    if existing is not None:
                        note.generation_version += 1
                    note.subject_code = subject_code
                    note.content_json = _insufficient_evidence_content(topic_name)
                    note.source_concept_ids_json = []
                    note.source_fact_ids_json = []
                    note.status = "insufficient_evidence"
                    note.error_message = None
                    db.add(note)
                    db.commit()
                    done_count += 1
                    continue

                records_json = serialize_knowledge_payload(
                    concepts=concepts, facts=facts, questions=questions
                )
                prompt_tmpl, prompt_text = self._render_note_prompt(
                    note_type=note_type,
                    topic_name=topic_name,
                    subject_code=subject_code,
                    adapter=adapter,
                    questions=questions,
                    records_json=records_json,
                )

                try:
                    llm_res = self.llm_provider.generate_structured_output(
                        GeneratedNoteOutput,
                        prompt_text,
                        system_instruction=prompt_tmpl.system_instruction,
                        model_tier="standard",
                        temperature=0.2,
                        prompt_name=prompt_tmpl.name,
                        prompt_version=prompt_tmpl.version,
                    )
                except (AIConfigurationError, AIProviderError) as exc:
                    code = (
                        "AI_CONFIG_ERROR"
                        if isinstance(exc, AIConfigurationError)
                        else "AI_PROVIDER_ERROR"
                    )
                    self._set_stage(
                        stages,
                        "generate_notes",
                        status="failed",
                        processed_items=done_count,
                        total_items=total_targets,
                        error_code=code,
                        error_message=str(exc),
                    )
                    self._fail_job(db, job, code, str(exc), stages)
                    return

                run = AIGenerationRun(
                    document_id=document.id,
                    job_id=job.id,
                    stage=f"note_generation:{note_type}",
                    model_name=llm_res.model_name,
                    prompt_name=llm_res.prompt_name,
                    prompt_version=llm_res.prompt_version,
                    latency_ms=llm_res.latency_ms,
                    token_usage_json=llm_res.token_usage,
                    validation_status=llm_res.status,
                    error_message=llm_res.error_message,
                )
                db.add(run)
                db.flush()

                note = existing or Note(
                    document_id=document.id,
                    topic_id=topic_id,
                    subject_code=subject_code,
                    note_type=note_type,
                    title=f"{topic_name} — {note_type.replace('_', ' ').title()}",
                )
                if existing is not None:
                    note.generation_version += 1

                note.subject_code = subject_code
                note.source_concept_ids_json = [str(c.id) for c in concepts]
                note.source_fact_ids_json = [str(f.id) for f in facts]
                note.model_name = llm_res.model_name
                note.prompt_name = llm_res.prompt_name
                note.prompt_version = llm_res.prompt_version
                note.generation_run_id = run.id

                if llm_res.parsed is None or llm_res.status == "failed_validation":
                    note.status = "failed"
                    note.error_message = llm_res.error_message or "Note schema validation failed"
                    note.content_json = {
                        "summary": "Generation failed validation.",
                        "sections": [],
                    }
                else:
                    outcome = validate_generated_note(
                        llm_res.parsed,
                        document_id=document.id,
                        subject_code=subject_code,
                        note_type=note_type,
                        facts=facts,
                        concepts=concepts,
                        detailed_reference=detailed_content,
                    )
                    if note_type == "detailed":
                        detailed_content = outcome.content
                    note.title = llm_res.parsed.title[:255]
                    note.content_json = outcome.content.model_dump(mode="json")
                    note.status = outcome.status
                    note.error_message = "; ".join(outcome.warnings) if outcome.warnings else None
                    validated_count += 1

                db.add(note)
                db.commit()
                done_count += 1
                self._set_stage(
                    stages,
                    "generate_notes",
                    status="running",
                    processed_items=done_count,
                    total_items=total_targets,
                )
                self._update_job(
                    db,
                    job,
                    stage="generate_notes",
                    stages=stages,
                    processed_items=done_count,
                    total_items=total_targets,
                )

        self._set_stage(
            stages,
            "generate_notes",
            status="completed",
            processed_items=total_targets,
            total_items=total_targets,
        )
        self._set_stage(
            stages,
            "validate_notes",
            status="completed",
            processed_items=validated_count,
            total_items=total_targets,
        )

        job.status = "completed"
        job.current_stage = "completed"
        job.finished_at = utcnow()
        job.processed_items = total_targets
        job.total_items = total_targets
        job.progress_percent = 100
        self._assign_stages(job, stages)
        db.add(job)
        db.commit()

    @staticmethod
    def _render_note_prompt(
        *,
        note_type: str,
        topic_name: str,
        subject_code: str,
        adapter: Any,
        questions: list[Question],
        records_json: str,
    ) -> tuple[Any, str]:
        if note_type == "quick_revision":
            tmpl = QUICK_REVISION_PROMPT_V1
            return tmpl, tmpl.render(
                topic_name=topic_name,
                subject_code=subject_code,
                knowledge_records_json=records_json,
            )
        if note_type == "formula_sheet":
            tmpl = FORMULA_SHEET_PROMPT_V1
            return tmpl, tmpl.render(
                topic_name=topic_name,
                subject_code=subject_code,
                knowledge_records_json=records_json,
            )
        if note_type == "strategy_sheet":
            tmpl = STRATEGY_SHEET_PROMPT_V1
            return tmpl, tmpl.render(
                topic_name=topic_name,
                subject_code=subject_code,
                subject_template_instructions=adapter.strategy_instructions(),
                knowledge_records_json=records_json,
            )

        tmpl = DETAILED_NOTES_PROMPT_V1
        blueprint = ", ".join(title for _, title in adapter.detailed_section_blueprint())
        exam_context = (
            f"Sample contains {len(questions)} extracted question(s) for this topic."
            if questions
            else "No PYQs supplied for this topic; do not claim exam weightage."
        )
        return tmpl, tmpl.render(
            topic_name=topic_name,
            subject_code=subject_code,
            exam_context=exam_context,
            section_blueprint=blueprint,
            knowledge_records_json=records_json,
        )


def run_note_generation_in_session(
    *,
    session_factory: sessionmaker[Session],
    document_id: UUID,
    job_id: UUID,
    llm_provider: LLMProvider,
    note_types: list[str],
    topic_ids: list[UUID] | None = None,
    force_regenerate: bool = False,
) -> None:
    """BackgroundTask entrypoint executing note generation inside its own session."""
    db = session_factory()
    try:
        document = db.get(Document, document_id)
        job = db.get(ProcessingJob, job_id)
        if document is None or job is None:
            return
        NoteGenerationPipeline(llm_provider).run(
            db,
            document,
            job,
            note_types=note_types,
            topic_ids=topic_ids,
            force_regenerate=force_regenerate,
        )
    except Exception as exc:
        logger.exception("Unhandled error generating notes for document %s", document_id)
        job = db.get(ProcessingJob, job_id)
        if job is not None and job.status not in ("completed", "failed"):
            job.status = "failed"
            job.error_code = "NOTE_GENERATION_ERROR"
            job.error_message = str(exc)
            job.finished_at = utcnow()
            db.add(job)
            db.commit()
    finally:
        db.close()
