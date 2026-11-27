from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.assessment import Question, QuestionOption
from app.repositories.question_repo import QuestionRepository
from app.schemas.question import (
    DeleteQuestionResponse,
    QuestionDetailOut,
    QuestionIngestionSummary,
    QuestionListResponse,
    QuestionOptionOut,
    QuestionOut,
    QuestionUpdateRequest,
)
from app.services.question_generation.deduplicator import (
    QuestionDeduplicator,
    compute_stem_hash,
    normalize_stem,
)
from app.services.question_validation.option_checks import check_single_choice_options
from app.services.question_validation.validator import QuestionValidationService

_ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}
_ALLOWED_QUESTION_TYPES = {"single_choice", "multiple_choice", "true_false", "numeric"}


def _read_attr(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _normalize_options(raw_options: Sequence[Any] | None) -> list[tuple[str, str]]:
    if not raw_options:
        return []
    normalized: list[tuple[str, str]] = []
    for item in raw_options:
        key = str(_read_attr(item, "key", "") or "").strip().upper()
        text = " ".join(str(_read_attr(item, "text", "") or "").split()).strip()
        if key or text:
            normalized.append((key, text))
    return normalized


def _resolve_topic_id(
    candidate: Any,
    topic_id_map: Mapping[str, UUID] | None,
) -> UUID | None:
    explicit_topic_id = _read_attr(candidate, "topic_id")
    if isinstance(explicit_topic_id, UUID):
        return explicit_topic_id
    if isinstance(explicit_topic_id, str) and explicit_topic_id.strip():
        try:
            return UUID(explicit_topic_id.strip())
        except ValueError:
            pass

    topic_name = _read_attr(candidate, "topic_name")
    if not topic_name or not topic_id_map:
        return None

    cleaned_name = str(topic_name).strip()
    if cleaned_name in topic_id_map:
        return topic_id_map[cleaned_name]

    lowered_lookup = {k.strip().lower(): v for k, v in topic_id_map.items()}
    return lowered_lookup.get(cleaned_name.lower())


def _sanitized_answer_data(raw_data: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(raw_data or {})
    data.pop("owner_user_id", None)
    return data


def _extract_warnings(question: Question) -> list[str]:
    answer_data = question.correct_answer_data or {}
    raw = answer_data.get("validation_warnings")
    if isinstance(raw, list):
        return [str(w) for w in raw]
    return []


def build_question_out(
    question: Question,
    *,
    topic_name: str | None,
    options: list[QuestionOption],
) -> QuestionOut:
    """Build a QuestionOut DTO without exposing internal storage-only keys."""
    answer_data = question.correct_answer_data or {}
    return QuestionOut(
        id=question.id,
        document_id=question.document_id,
        topic_id=question.topic_id,
        topic_name=topic_name,
        concept_id=question.concept_id,
        exam_config_id=question.exam_config_id,
        subject_code=question.subject_code,
        question_text=question.question_text,
        question_type=question.question_type,
        difficulty=question.difficulty,
        origin=question.origin,
        source_page_number=question.source_page_number,
        supporting_excerpt=question.supporting_excerpt,
        diagram_asset_id=question.diagram_asset_id,
        passage_group_id=question.passage_group_id,
        passage_text=question.passage_text,
        pyq_metadata_json=question.pyq_metadata_json,
        options=[QuestionOptionOut.model_validate(opt) for opt in options],
        correct_option_key=answer_data.get("correct_option_key"),
        explanation=question.explanation,
        answer_key_provenance=question.answer_key_provenance,
        validation_status=question.validation_status,
        validation_warnings=_extract_warnings(question),
        model_name=question.model_name,
        prompt_name=question.prompt_name,
        prompt_version=question.prompt_version,
        created_at=question.created_at,
        updated_at=question.updated_at,
    )


def build_question_detail_out(
    question: Question,
    *,
    topic_name: str | None,
    options: list[QuestionOption],
) -> QuestionDetailOut:
    """Build a full QuestionDetailOut DTO for Question Bank inspection."""
    base = build_question_out(question, topic_name=topic_name, options=options)
    return QuestionDetailOut(
        **base.model_dump(),
        correct_answer_data=_sanitized_answer_data(question.correct_answer_data),
    )


class QuestionAccessDeniedError(Exception):
    """Raised when a user accesses a question or document they do not own."""


class QuestionDocumentNotFoundError(Exception):
    """Raised when a referenced document does not exist or was deleted."""


class QuestionNotFoundError(Exception):
    """Raised when a requested question does not exist."""


class QuestionInvalidReferenceError(Exception):
    """Raised when a referenced topic, exam config, or update payload is invalid."""


class QuestionIngestionService:
    """Validates, deduplicates, queries, edits, and persists Question Bank items."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = QuestionRepository(db)
        self._validator = QuestionValidationService()

    def ingest_candidates(
        self,
        document_id: UUID,
        candidates: Sequence[Any],
        topic_id_map: Mapping[str, UUID] | None = None,
    ) -> QuestionIngestionSummary:
        """Deduplicate, validate provenance/options/math, and store extracted questions."""
        document = self._repo.get_document_for_ownership(document_id)
        if document is None:
            raise QuestionDocumentNotFoundError(f"Document '{document_id}' not found")

        existing_rows = self._repo.list_existing_stems_for_user(document.user_id)
        deduplicator = QuestionDeduplicator(existing_rows)

        inserted_ids: list[UUID] = []
        skipped_duplicate_count = 0
        verified_count = 0
        needs_review_count = 0

        default_subject = document.subject_code or document.detected_subject_code or "unknown"

        for candidate in candidates:
            raw_stem = str(_read_attr(candidate, "question_text", "") or "").strip()
            if not raw_stem:
                continue

            dup_res = deduplicator.check(raw_stem)
            if dup_res.is_duplicate:
                skipped_duplicate_count += 1
                continue

            stem_hash = compute_stem_hash(raw_stem)

            raw_type = str(
                _read_attr(candidate, "question_type", "single_choice") or "single_choice"
            )
            question_type = raw_type.strip().lower()
            if question_type not in _ALLOWED_QUESTION_TYPES:
                question_type = "single_choice"

            raw_difficulty = str(_read_attr(candidate, "difficulty", "medium") or "medium").lower()
            difficulty = raw_difficulty if raw_difficulty in _ALLOWED_DIFFICULTIES else "medium"

            subject_code = (
                str(_read_attr(candidate, "subject_code", "") or "").strip() or default_subject
            )
            topic_id = _resolve_topic_id(candidate, topic_id_map)

            options = _normalize_options(_read_attr(candidate, "options", []))
            option_keys = [key for key, _ in options]

            raw_correct_key = _read_attr(candidate, "correct_option_key")
            correct_key = str(raw_correct_key).strip().upper() if raw_correct_key else None

            supporting_excerpt = _read_attr(candidate, "supporting_excerpt")
            cleaned_excerpt = str(supporting_excerpt).strip() if supporting_excerpt else None

            provenance = str(
                _read_attr(candidate, "answer_key_provenance", "source_answer_key")
                or "source_answer_key"
            ).strip()
            explanation = str(_read_attr(candidate, "explanation", "") or "").strip()

            outcome = self._validator.validate_question(
                question_text=raw_stem,
                question_type=question_type,
                subject_code=subject_code,
                options=options,
                correct_option_key=correct_key,
                explanation=explanation,
                origin="extracted",
                answer_key_provenance=provenance,
                supporting_excerpt=cleaned_excerpt,
                run_llm_verify=False,
            )

            has_valid_key = bool(correct_key and correct_key in option_keys)
            final_provenance = outcome.answer_key_provenance
            if not has_valid_key and final_provenance != "conflicting":
                final_provenance = "unverified"

            correct_answer_data: dict[str, Any] = {}
            if has_valid_key:
                correct_answer_data["correct_option_key"] = correct_key
            if outcome.warnings:
                correct_answer_data["validation_warnings"] = outcome.warnings

            if outcome.validation_status == "verified":
                verified_count += 1
            else:
                needs_review_count += 1

            concept_id = _read_attr(candidate, "concept_id")
            exam_config_id = _read_attr(candidate, "exam_config_id") or document.exam_config_id
            diagram_asset_id = _read_attr(candidate, "diagram_asset_id")
            passage_group_id = _read_attr(candidate, "passage_group_id")

            question = Question(
                document_id=document_id,
                topic_id=topic_id,
                concept_id=concept_id if isinstance(concept_id, UUID) else None,
                exam_config_id=exam_config_id if isinstance(exam_config_id, UUID) else None,
                subject_code=subject_code,
                question_text=raw_stem,
                question_type=question_type,
                difficulty=difficulty,
                origin="extracted",
                source_page_number=_read_attr(candidate, "source_page_number"),
                supporting_excerpt=cleaned_excerpt,
                diagram_asset_id=diagram_asset_id if isinstance(diagram_asset_id, UUID) else None,
                passage_group_id=passage_group_id if isinstance(passage_group_id, UUID) else None,
                passage_text=_read_attr(candidate, "passage_text"),
                pyq_metadata_json=_read_attr(candidate, "pyq_metadata"),
                stem_hash=stem_hash,
                correct_answer_data=correct_answer_data,
                explanation=explanation,
                answer_key_provenance=final_provenance,
                validation_status=outcome.validation_status,
                model_name=_read_attr(candidate, "model_name"),
                prompt_name=_read_attr(candidate, "prompt_name"),
                prompt_version=_read_attr(candidate, "prompt_version"),
            )

            option_models = [
                QuestionOption(
                    option_key=key,
                    option_text=text,
                    display_order=idx,
                )
                for idx, (key, text) in enumerate(options)
            ]
            self._repo.create_question_with_options(question, option_models)
            deduplicator.register(question.id, stem_hash, raw_stem)
            inserted_ids.append(question.id)

        self._repo.commit()

        return QuestionIngestionSummary(
            document_id=document_id,
            total_received=len(candidates),
            inserted_count=len(inserted_ids),
            skipped_duplicate_count=skipped_duplicate_count,
            verified_count=verified_count,
            needs_review_count=needs_review_count,
            question_ids=inserted_ids,
        )

    def list_questions(
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
    ) -> QuestionListResponse:
        """List questions visible to the user, enforcing document ownership if scoped."""
        if document_id is not None:
            document = self._repo.get_document_for_ownership(document_id)
            if document is None:
                raise QuestionDocumentNotFoundError(f"Document '{document_id}' not found")
            if document.user_id != user_id:
                raise QuestionAccessDeniedError("You do not have access to this document")

        rows, options_by_question, total = self._repo.list_questions_for_user(
            user_id,
            document_id=document_id,
            subject_code=subject_code,
            topic_id=topic_id,
            difficulty=difficulty,
            origin=origin,
            validation_status=validation_status,
            pyq_year=pyq_year,
            q=q,
            limit=limit,
            offset=offset,
        )

        items = [
            build_question_out(
                question,
                topic_name=topic_name,
                options=options_by_question.get(question.id, []),
            )
            for question, topic_name in rows
        ]

        return QuestionListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_question(self, *, question_id: UUID, user_id: UUID) -> QuestionDetailOut:
        """Return full Question Bank detail for an owned question."""
        loaded = self._repo.get_question_with_options(question_id)
        if loaded is None:
            raise QuestionNotFoundError(f"Question '{question_id}' not found")
        question, topic_name, options = loaded
        if not self._repo.is_owned_by_user(question, user_id):
            raise QuestionAccessDeniedError("You do not have access to this question")
        return build_question_detail_out(question, topic_name=topic_name, options=options)

    def update_question(
        self,
        *,
        question_id: UUID,
        user_id: UUID,
        payload: QuestionUpdateRequest,
    ) -> QuestionDetailOut:
        """Manually edit or confirm review status of an owned Question Bank item."""
        loaded = self._repo.get_question_with_options(question_id)
        if loaded is None:
            raise QuestionNotFoundError(f"Question '{question_id}' not found")
        question, topic_name, options = loaded
        if not self._repo.is_owned_by_user(question, user_id):
            raise QuestionAccessDeniedError("You do not have access to this question")

        if payload.topic_id is not None:
            topic = self._repo.get_topic_by_id(payload.topic_id)
            if topic is None:
                raise QuestionInvalidReferenceError(f"Topic '{payload.topic_id}' not found")
            question.topic_id = topic.id
            topic_name = topic.name

        if payload.question_text is not None:
            cleaned_stem = " ".join(payload.question_text.split()).strip()
            if len(cleaned_stem) < 5:
                raise QuestionInvalidReferenceError("question_text must be at least 5 characters")
            question.question_text = cleaned_stem
            question.stem_hash = compute_stem_hash(cleaned_stem)

        if payload.difficulty is not None:
            question.difficulty = payload.difficulty

        if payload.explanation is not None:
            question.explanation = payload.explanation.strip()

        option_pairs = [(opt.option_key, opt.option_text) for opt in options]
        if payload.options is not None:
            option_pairs = [
                (opt.key.strip().upper(), " ".join(opt.text.split()).strip())
                for opt in payload.options
            ]
            new_options = [
                QuestionOption(option_key=k, option_text=t, display_order=idx)
                for idx, (k, t) in enumerate(option_pairs)
            ]
            options = self._repo.replace_options(question.id, new_options)

        answer_data = dict(question.correct_answer_data or {})
        old_key = answer_data.get("correct_option_key")
        if payload.correct_option_key is not None:
            new_key = payload.correct_option_key.strip().upper()
            answer_data["correct_option_key"] = new_key
            if new_key != old_key:
                question.answer_key_provenance = "manual"
            elif question.answer_key_provenance in ("unverified", "conflicting"):
                question.answer_key_provenance = "manual"

        current_key = answer_data.get("correct_option_key")
        if question.question_type == "single_choice":
            opt_check = check_single_choice_options(option_pairs, current_key)
            if payload.validation_status == "verified" and not opt_check.is_valid:
                raise QuestionInvalidReferenceError(
                    "Cannot mark question as verified: " + "; ".join(opt_check.warnings)
                )

        outcome = self._validator.validate_question(
            question_text=question.question_text,
            question_type=question.question_type,
            subject_code=question.subject_code,
            options=option_pairs,
            correct_option_key=current_key,
            explanation=question.explanation,
            origin=question.origin,
            answer_key_provenance=question.answer_key_provenance,
            supporting_excerpt=question.supporting_excerpt
            or (question.question_text if question.document_id is None else None),
            run_llm_verify=False,
        )
        answer_data["validation_warnings"] = outcome.warnings
        question.correct_answer_data = answer_data

        if payload.validation_status is not None:
            question.validation_status = payload.validation_status
            if payload.validation_status == "verified" and question.answer_key_provenance in (
                "unverified",
                "conflicting",
                "user_supplied",
            ):
                question.answer_key_provenance = "manual"
                answer_data["validation_warnings"] = []
                question.correct_answer_data = answer_data
        else:
            question.validation_status = outcome.validation_status

        self._repo.commit()
        self._db.refresh(question)
        return build_question_detail_out(question, topic_name=topic_name, options=options)

    def delete_question(self, *, question_id: UUID, user_id: UUID) -> DeleteQuestionResponse:
        """Delete an owned Question Bank item."""
        loaded = self._repo.get_question_with_options(question_id)
        if loaded is None:
            raise QuestionNotFoundError(f"Question '{question_id}' not found")
        question, _, _ = loaded
        if not self._repo.is_owned_by_user(question, user_id):
            raise QuestionAccessDeniedError("You do not have access to this question")
        self._repo.delete_question(question)
        return DeleteQuestionResponse(deleted_id=question_id)


__all__ = [
    "QuestionAccessDeniedError",
    "QuestionDocumentNotFoundError",
    "QuestionIngestionService",
    "QuestionInvalidReferenceError",
    "QuestionNotFoundError",
    "build_question_detail_out",
    "build_question_out",
    "compute_stem_hash",
    "normalize_stem",
]
