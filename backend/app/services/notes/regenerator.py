from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.prompts.notes import NOTE_REGENERATE_PROMPT_V1
from app.ai.provider import LLMProvider
from app.ai.schemas.notes import GeneratedNoteOutput
from app.models.document import Document
from app.models.learning import AIGenerationRun, Note, Topic
from app.repositories.notes_repo import NotesRepository
from app.schemas.notes import NoteContentJson
from app.services.notes.generator import (
    _insufficient_evidence_content,
    serialize_knowledge_payload,
)
from app.services.notes.validators import validate_generated_note
from app.services.subjects.registry import SUBJECT_ADAPTER_REGISTRY


class NoteRegenerator:
    """Regenerates a single note or selected sections strictly from stored knowledge records."""

    def __init__(self, db: Session, llm_provider: LLMProvider) -> None:
        self.db = db
        self.llm_provider = llm_provider
        self.repo = NotesRepository(db)

    def regenerate_note(
        self,
        note: Note,
        document: Document,
        *,
        section_keys: list[str] | None = None,
        custom_instruction: str | None = None,
    ) -> Note:
        topic = self.db.get(Topic, note.topic_id) if note.topic_id is not None else None
        topic_name = topic.name if topic is not None else "General Document Notes"
        subject_code = note.subject_code or document.subject_code or "unknown"
        adapter = SUBJECT_ADAPTER_REGISTRY.get(subject_code)

        concepts, facts, questions = self.repo.get_document_knowledge_scope(
            document_id=document.id,
            topic_id=note.topic_id,
        )

        if not concepts and not facts:
            note.generation_version += 1
            note.status = "insufficient_evidence"
            note.content_json = _insufficient_evidence_content(topic_name)
            note.error_message = None
            self.db.add(note)
            self.db.commit()
            self.db.refresh(note)
            return note

        records_json = serialize_knowledge_payload(
            concepts=concepts, facts=facts, questions=questions
        )
        prompt = NOTE_REGENERATE_PROMPT_V1.render(
            note_type=note.note_type,
            topic_name=topic_name,
            subject_code=subject_code,
            section_keys=", ".join(section_keys) if section_keys else "all",
            custom_instruction=custom_instruction or "none",
            subject_guidance=adapter.strategy_instructions(),
            knowledge_records_json=records_json,
        )

        llm_res = self.llm_provider.generate_structured_output(
            GeneratedNoteOutput,
            prompt,
            system_instruction=NOTE_REGENERATE_PROMPT_V1.system_instruction,
            model_tier="standard",
            temperature=0.2,
            prompt_name=NOTE_REGENERATE_PROMPT_V1.name,
            prompt_version=NOTE_REGENERATE_PROMPT_V1.version,
        )

        run = AIGenerationRun(
            document_id=document.id,
            job_id=None,
            stage=f"note_regenerate:{note.note_type}",
            model_name=llm_res.model_name,
            prompt_name=llm_res.prompt_name,
            prompt_version=llm_res.prompt_version,
            latency_ms=llm_res.latency_ms,
            token_usage_json=llm_res.token_usage,
            validation_status=llm_res.status,
            error_message=llm_res.error_message,
        )
        self.db.add(run)
        self.db.flush()

        note.generation_version += 1
        note.model_name = llm_res.model_name
        note.prompt_name = llm_res.prompt_name
        note.prompt_version = llm_res.prompt_version
        note.generation_run_id = run.id
        note.source_concept_ids_json = [str(c.id) for c in concepts]
        note.source_fact_ids_json = [str(f.id) for f in facts]

        if llm_res.parsed is None or llm_res.status == "failed_validation":
            note.status = "failed"
            note.error_message = llm_res.error_message or "Note regeneration failed validation"
            self.db.add(note)
            self.db.commit()
            self.db.refresh(note)
            return note

        detailed_ref: NoteContentJson | None = None
        if note.note_type == "quick_revision":
            detailed_note = self.repo.find_existing_note(
                document_id=document.id,
                topic_id=note.topic_id,
                note_type="detailed",
            )
            if detailed_note is not None and detailed_note.content_json:
                try:
                    detailed_ref = NoteContentJson.model_validate(detailed_note.content_json)
                except Exception:
                    detailed_ref = None

        outcome = validate_generated_note(
            llm_res.parsed,
            document_id=document.id,
            subject_code=subject_code,
            note_type=note.note_type,
            facts=facts,
            concepts=concepts,
            detailed_reference=detailed_ref,
        )

        if section_keys:
            target_keys = set(section_keys)
            existing_content = NoteContentJson.model_validate(
                note.content_json or {"summary": outcome.content.summary, "sections": []}
            )
            new_by_key = {
                sec.key: sec for sec in outcome.content.sections if sec.key in target_keys
            }
            merged_sections = [
                new_by_key.get(sec.key, sec) for sec in existing_content.sections
            ]
            existing_keys = {sec.key for sec in existing_content.sections}
            for sec in outcome.content.sections:
                if sec.key in target_keys and sec.key not in existing_keys:
                    merged_sections.append(sec)
            existing_content.sections = merged_sections
            note.content_json = existing_content.model_dump(mode="json")
        else:
            note.title = llm_res.parsed.title[:255]
            note.content_json = outcome.content.model_dump(mode="json")

        note.status = outcome.status
        note.error_message = "; ".join(outcome.warnings) if outcome.warnings else None
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note
