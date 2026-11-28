from __future__ import annotations

import csv
import io
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.provider import LLMProvider
from app.models.assessment import Question, QuestionOption
from app.repositories.question_repo import QuestionRepository
from app.schemas.question import (
    PYQImportItem,
    QuestionDetailOut,
    QuestionImportRequest,
    QuestionImportResponse,
    QuestionOptionInput,
)
from app.services.question_generation.deduplicator import (
    QuestionDeduplicator,
    compute_stem_hash,
)
from app.services.question_generation.ingestion import (
    QuestionAccessDeniedError,
    QuestionDocumentNotFoundError,
    QuestionInvalidReferenceError,
    build_question_detail_out,
)
from app.services.question_validation.validator import QuestionValidationService


def parse_csv_pyq_items(csv_text: str) -> list[PYQImportItem]:
    """Parse structured CSV rows into `PYQImportItem` objects.

    Expected columns (case-insensitive):
    `question_text`, `option_a`, `option_b`, `option_c`, `option_d`,
    optional `correct_option_key`, `explanation`, `subject_code`, `topic_name`,
    `difficulty`, `source_page_number`, `year`, `shift`, `tier`, `paper_question_no`,
    `passage_text`, `supporting_excerpt`.
    """
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff").strip()))
    items: list[PYQImportItem] = []
    for row in reader:
        norm = {str(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        q_text = norm.get("question_text", "")
        if not q_text:
            continue

        options: list[QuestionOptionInput] = []
        col_map = (("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d"))
        for key, col in col_map:
            val = norm.get(col, "")
            if val:
                options.append(QuestionOptionInput(key=key, text=val))

        pyq_meta: dict[str, Any] = {}
        if norm.get("year"):
            try:
                pyq_meta["year"] = int(norm["year"])
            except ValueError:
                pyq_meta["year"] = norm["year"]
        if norm.get("shift"):
            pyq_meta["shift"] = norm["shift"]
        if norm.get("tier"):
            pyq_meta["tier"] = norm["tier"]
        if norm.get("paper_question_no"):
            pyq_meta["paper_question_no"] = norm["paper_question_no"]

        source_page: int | None = None
        if norm.get("source_page_number"):
            try:
                source_page = int(norm["source_page_number"])
            except ValueError:
                source_page = None

        raw_diff = norm.get("difficulty", "medium").lower()
        difficulty = raw_diff if raw_diff in ("easy", "medium", "hard") else "medium"

        items.append(
            PYQImportItem(
                question_text=q_text,
                options=options,
                correct_option_key=norm.get("correct_option_key") or None,
                explanation=norm.get("explanation", ""),
                subject_code=norm.get("subject_code") or norm.get("subject") or None,
                topic_name=norm.get("topic_name") or None,
                difficulty=difficulty,  # type: ignore[arg-type]
                source_page_number=source_page,
                supporting_excerpt=norm.get("supporting_excerpt") or None,
                pyq_metadata=pyq_meta or None,
                passage_text=norm.get("passage_text") or None,
            )
        )
    return items


class PYQImportService:
    """Imports structured JSON or CSV PYQ batches with deduplication & validation."""

    def __init__(self, db: Session, llm_provider: LLMProvider | None = None) -> None:
        self._db = db
        self._repo = QuestionRepository(db)
        self._validator = QuestionValidationService(llm_provider=llm_provider)

    def import_questions(
        self,
        *,
        user_id: UUID,
        payload: QuestionImportRequest,
    ) -> QuestionImportResponse:
        """Validate, deduplicate, and persist a batch of PYQ items."""
        document = None
        if payload.document_id is not None:
            document = self._repo.get_document_for_ownership(payload.document_id)
            if document is None:
                raise QuestionDocumentNotFoundError(f"Document '{payload.document_id}' not found")
            if document.user_id != user_id:
                raise QuestionAccessDeniedError("You do not have access to this document")

        if payload.exam_config_id is not None and not self._repo.exam_config_exists(
            payload.exam_config_id
        ):
            raise QuestionInvalidReferenceError(
                f"Exam config '{payload.exam_config_id}' not found"
            )

        raw_items = list(payload.items)
        if not raw_items and payload.csv_content:
            raw_items = parse_csv_pyq_items(payload.csv_content)

        if not raw_items:
            raise QuestionInvalidReferenceError(
                "No importable question items provided in `items` or `csv_content`."
            )

        existing_stems = self._repo.list_existing_stems_for_user(user_id)
        deduplicator = QuestionDeduplicator(existing_stems)

        passage_groups: dict[str, UUID] = {}
        imported_details: list[QuestionDetailOut] = []
        verified_count = 0
        needs_review_count = 0
        duplicates_skipped = 0

        for item in raw_items:
            cleaned_stem = " ".join(item.question_text.split()).strip()
            if not cleaned_stem:
                continue

            dup_res = deduplicator.check(cleaned_stem)
            if dup_res.is_duplicate:
                duplicates_skipped += 1
                continue

            subject_code = (
                (item.subject_code or "").strip()
                or payload.default_subject_code.strip()
                or (document.subject_code if document else None)
                or (document.detected_subject_code if document else None)
                or "unknown"
            )
            exam_config_id = payload.exam_config_id or (
                document.exam_config_id if document else None
            )

            option_pairs = [
                (opt.key.strip().upper(), " ".join(opt.text.split()).strip())
                for opt in item.options
            ]

            excerpt = item.supporting_excerpt
            if excerpt is None and payload.document_id is None:
                # Standalone structured import has no document excerpt requirement.
                excerpt = cleaned_stem[:200]

            origin_value = (
                "extracted" if payload.answer_key_provenance == "source_answer_key" else "manual"
            )
            outcome = self._validator.validate_question(
                question_text=cleaned_stem,
                question_type="single_choice",
                subject_code=subject_code,
                options=option_pairs,
                correct_option_key=item.correct_option_key,
                explanation=item.explanation,
                origin=origin_value,
                answer_key_provenance=payload.answer_key_provenance,
                supporting_excerpt=excerpt,
                run_llm_verify=False,
            )

            topic_id: UUID | None = None
            topic_name: str | None = None
            if item.topic_name:
                topic = self._repo.get_or_create_topic(
                    subject_code=subject_code,
                    topic_name=item.topic_name,
                    exam_config_id=exam_config_id,
                )
                if topic is not None:
                    topic_id = topic.id
                    topic_name = topic.name

            passage_group_id = item.passage_group_id
            if passage_group_id is None and item.passage_text and item.passage_text.strip():
                norm_passage = " ".join(item.passage_text.split()).strip()
                passage_group_id = passage_groups.setdefault(norm_passage, uuid.uuid4())

            stem_hash = compute_stem_hash(cleaned_stem)
            answer_data: dict[str, Any] = {}
            if item.correct_option_key:
                answer_data["correct_option_key"] = item.correct_option_key.strip().upper()
            if outcome.warnings:
                answer_data["validation_warnings"] = outcome.warnings
            if payload.document_id is None:
                answer_data["owner_user_id"] = str(user_id)

            question = Question(
                document_id=payload.document_id,
                topic_id=topic_id,
                exam_config_id=exam_config_id,
                subject_code=subject_code,
                question_text=cleaned_stem,
                question_type="single_choice",
                difficulty=item.difficulty,
                origin=origin_value,
                source_page_number=item.source_page_number,
                supporting_excerpt=item.supporting_excerpt,
                passage_group_id=passage_group_id,
                passage_text=item.passage_text,
                pyq_metadata_json=item.pyq_metadata,
                stem_hash=stem_hash,
                correct_answer_data=answer_data,
                explanation=item.explanation.strip(),
                answer_key_provenance=outcome.answer_key_provenance,
                validation_status=outcome.validation_status,
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

            imported_details.append(
                build_question_detail_out(
                    question,
                    topic_name=topic_name,
                    options=option_models,
                )
            )

        self._repo.commit()

        return QuestionImportResponse(
            imported_count=len(imported_details),
            verified_count=verified_count,
            needs_review_count=needs_review_count,
            duplicates_skipped=duplicates_skipped,
            items=imported_details,
        )
