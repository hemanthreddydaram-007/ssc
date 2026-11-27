from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.provider import LLMProvider
from app.models.assessment import Question, QuestionOption
from app.models.learning import AIGenerationRun
from app.repositories.question_repo import QuestionRepository
from app.schemas.question import (
    QuestionDetailOut,
    QuestionGenerateRequest,
    QuestionGenerateResponse,
)
from app.services.question_generation.deduplicator import (
    QuestionDeduplicator,
    compute_stem_hash,
)
from app.services.question_generation.ingestion import (
    QuestionAccessDeniedError,
    QuestionDocumentNotFoundError,
    build_question_detail_out,
)
from app.services.question_validation.validator import QuestionValidationService


class GeneratedMCQOptionSchema(BaseModel):
    """Structured option returned by the LLM MCQ generator."""

    key: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1)


class GeneratedMCQItemSchema(BaseModel):
    """Single generated MCQ item returned by the LLM."""

    question_text: str = Field(min_length=5)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    topic_name: str | None = None
    options: list[GeneratedMCQOptionSchema] = Field(default_factory=list)
    correct_option_key: str | None = None
    explanation: str = ""
    source_page_number: int | None = None
    supporting_excerpt: str | None = None


class GeneratedMCQBatchSchema(BaseModel):
    """Batch container for structured MCQ generation."""

    questions: list[GeneratedMCQItemSchema] = Field(min_length=1)


class NoSourceKnowledgeError(Exception):
    """Raised when no stored concepts or facts exist for the requested generation scope."""


class QuestionGenerationFailedError(Exception):
    """Raised when LLM MCQ generation fails Pydantic schema validation after retry."""


_MCQ_SYSTEM_INSTRUCTION = (
    "You are an expert competitive-exam question author. Generate rigorous single-choice MCQs "
    "strictly grounded in the provided concepts and facts. Each question MUST have 4 distinct "
    "options keyed A, B, C, D, exactly one unambiguous correct option, and a step-by-step "
    "explanation. Return ONLY schema-conforming JSON."
)


class QuestionGenerationService:
    """Generates, validates, deduplicates, and stores source-grounded MCQs."""

    PROMPT_NAME = "question_generate"
    PROMPT_VERSION = "v1"

    def __init__(self, db: Session, llm_provider: LLMProvider) -> None:
        self._db = db
        self._repo = QuestionRepository(db)
        self._llm = llm_provider
        self._validator = QuestionValidationService(llm_provider=llm_provider)

    def generate(
        self,
        *,
        user_id: UUID,
        payload: QuestionGenerateRequest,
    ) -> QuestionGenerateResponse:
        """Generate new MCQs from stored knowledge, validate them, and persist."""
        document = None
        if payload.document_id is not None:
            document = self._repo.get_document_for_ownership(payload.document_id)
            if document is None:
                raise QuestionDocumentNotFoundError(f"Document '{payload.document_id}' not found")
            if document.user_id != user_id:
                raise QuestionAccessDeniedError("You do not have access to this document")

        concepts, facts, topics_by_id = self._repo.load_knowledge_for_generation(
            user_id,
            document_id=payload.document_id,
            topic_id=payload.topic_id,
            concept_id=payload.concept_id,
            subject_code=payload.subject_code,
        )

        if not concepts and not facts:
            raise NoSourceKnowledgeError(
                "No stored concepts or facts found for the requested scope. "
                "Extract knowledge from a document first."
            )

        inferred_subject = payload.subject_code
        if not inferred_subject and payload.topic_id and payload.topic_id in topics_by_id:
            inferred_subject = topics_by_id[payload.topic_id].subject_code
        if not inferred_subject and document is not None:
            inferred_subject = document.subject_code or document.detected_subject_code
        if not inferred_subject and topics_by_id:
            inferred_subject = next(iter(topics_by_id.values())).subject_code
        subject_code = inferred_subject or "unknown"

        knowledge_payload = {
            "subject_code": subject_code,
            "target_difficulty": payload.difficulty,
            "requested_count": payload.count,
            "topics": [
                {"id": str(t.id), "name": t.name, "subject_code": t.subject_code}
                for t in topics_by_id.values()
            ],
            "concepts": [
                {
                    "title": c.title,
                    "explanation": c.explanation,
                    "topic_name": topics_by_id[c.topic_id].name
                    if c.topic_id and c.topic_id in topics_by_id
                    else None,
                    "source_refs": c.source_refs_json,
                }
                for c in concepts[:12]
            ],
            "facts": [
                {
                    "fact_type": f.fact_type,
                    "content": f.content,
                    "source_page_number": f.source_page_number,
                    "supporting_excerpt": f.supporting_excerpt,
                    "topic_name": topics_by_id[f.topic_id].name
                    if f.topic_id and f.topic_id in topics_by_id
                    else None,
                }
                for f in facts[:20]
            ],
        }

        prompt = (
            f"Generate {payload.count} single-choice MCQs for subject '{subject_code}' "
            f"with difficulty '{payload.difficulty}'.\n"
            "Ground each question in the stored knowledge records below and cite "
            "source_page_number and supporting_excerpt when available.\n\n"
            f"Knowledge records:\n{json.dumps(knowledge_payload, ensure_ascii=True)}"
        )

        llm_result = self._llm.generate_structured_output(
            GeneratedMCQBatchSchema,
            prompt,
            system_instruction=_MCQ_SYSTEM_INSTRUCTION,
            model_tier="standard",
            temperature=0.2,
            prompt_name=self.PROMPT_NAME,
            prompt_version=self.PROMPT_VERSION,
        )

        self._repo.record_ai_run(
            AIGenerationRun(
                document_id=payload.document_id,
                job_id=None,
                stage="question_generation",
                model_name=llm_result.model_name,
                prompt_name=llm_result.prompt_name,
                prompt_version=llm_result.prompt_version,
                latency_ms=llm_result.latency_ms,
                token_usage_json=llm_result.token_usage,
                validation_status=llm_result.status,
                error_message=llm_result.error_message,
            )
        )

        if llm_result.status == "failed_validation" or llm_result.parsed is None:
            self._repo.commit()
            raise QuestionGenerationFailedError(
                llm_result.error_message
                or "AI question generation failed schema validation after repair retry."
            )

        existing_stems = self._repo.list_existing_stems_for_user(
            user_id,
            subject_code=subject_code if subject_code != "unknown" else None,
        )
        deduplicator = QuestionDeduplicator(existing_stems)

        evidence_texts = [f.content for f in facts[:10]] + [
            f"{c.title}: {c.explanation}" for c in concepts[:6]
        ]

        topic_by_name = {t.name.strip().lower(): t for t in topics_by_id.values()}
        primary_doc_id = payload.document_id or (
            concepts[0].document_id if concepts else facts[0].document_id
        )

        created_details: list[QuestionDetailOut] = []
        verified_count = 0
        needs_review_count = 0
        duplicates_skipped = 0

        for item in llm_result.parsed.questions[: payload.count]:
            cleaned_stem = " ".join(item.question_text.split()).strip()
            if not cleaned_stem:
                continue

            dup_res = deduplicator.check(cleaned_stem)
            if dup_res.is_duplicate:
                duplicates_skipped += 1
                continue

            option_pairs = [
                (opt.key.strip().upper(), " ".join(opt.text.split()).strip())
                for opt in item.options
            ]

            outcome = self._validator.validate_question(
                question_text=cleaned_stem,
                question_type="single_choice",
                subject_code=subject_code,
                options=option_pairs,
                correct_option_key=item.correct_option_key,
                explanation=item.explanation,
                origin="generated",
                answer_key_provenance="ai_verified",
                supporting_excerpt=item.supporting_excerpt,
                evidence_texts=evidence_texts,
                run_llm_verify=True,
            )

            resolved_topic_id = payload.topic_id
            resolved_topic_name: str | None = None
            if resolved_topic_id and resolved_topic_id in topics_by_id:
                resolved_topic_name = topics_by_id[resolved_topic_id].name
            elif item.topic_name:
                matched_topic = topic_by_name.get(item.topic_name.strip().lower())
                if matched_topic is not None:
                    resolved_topic_id = matched_topic.id
                    resolved_topic_name = matched_topic.name
                else:
                    created_topic = self._repo.get_or_create_topic(
                        subject_code=subject_code,
                        topic_name=item.topic_name,
                        exam_config_id=document.exam_config_id if document else None,
                    )
                    if created_topic is not None:
                        resolved_topic_id = created_topic.id
                        resolved_topic_name = created_topic.name

            stem_hash = compute_stem_hash(cleaned_stem)
            answer_data: dict[str, Any] = {}
            if item.correct_option_key:
                answer_data["correct_option_key"] = item.correct_option_key.strip().upper()
            if outcome.warnings:
                answer_data["validation_warnings"] = outcome.warnings
            if primary_doc_id is None:
                answer_data["owner_user_id"] = str(user_id)

            question = Question(
                document_id=primary_doc_id,
                topic_id=resolved_topic_id,
                concept_id=payload.concept_id or (concepts[0].id if concepts else None),
                exam_config_id=document.exam_config_id if document else None,
                subject_code=subject_code,
                question_text=cleaned_stem,
                question_type="single_choice",
                difficulty=item.difficulty,
                origin="generated",
                source_page_number=item.source_page_number,
                supporting_excerpt=item.supporting_excerpt,
                stem_hash=stem_hash,
                correct_answer_data=answer_data,
                explanation=item.explanation.strip(),
                answer_key_provenance=outcome.answer_key_provenance,
                validation_status=outcome.validation_status,
                model_name=llm_result.model_name,
                prompt_name=llm_result.prompt_name,
                prompt_version=llm_result.prompt_version,
            )
            option_models = [
                QuestionOption(
                    option_key=key,
                    option_text=text,
                    display_order=idx,
                )
                for idx, (key, text) in enumerate(option_pairs)
            ]
            self._repo.create_question_with_options(question, option_models)
            deduplicator.register(question.id, stem_hash, cleaned_stem)

            if outcome.validation_status == "verified":
                verified_count += 1
            else:
                needs_review_count += 1

            created_details.append(
                build_question_detail_out(
                    question,
                    topic_name=resolved_topic_name,
                    options=option_models,
                )
            )

        self._repo.commit()

        return QuestionGenerateResponse(
            created=created_details,
            verified_count=verified_count,
            needs_review_count=needs_review_count,
            duplicates_skipped=duplicates_skipped,
        )
