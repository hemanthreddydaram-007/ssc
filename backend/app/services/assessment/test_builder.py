from __future__ import annotations

import random
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.assessment import Question, QuestionOption, Test, TestQuestion
from app.repositories.test_repo import TestRepository
from app.schemas.test import (
    DifficultyMix,
    TestCreateRequest,
    TestListResponse,
    TestOut,
    TestPreviewRequest,
    TestPreviewResponse,
)
from app.services.assessment.attempt_engine import AttemptEngine
from app.services.assessment.scoring_service import AttemptPostSubmitHook, noop_post_submit_hook
from app.services.assessment.timer_service import ClockFn, utcnow_clock


class TestNotFoundError(Exception):
    """Raised when a test does not exist."""


class TestAccessDeniedError(Exception):
    """Raised when a user accesses a test owned by another user."""


class TestBuildValidationError(Exception):
    """Raised when test creation parameters or available questions cannot satisfy the request."""


def _allocate_difficulty_targets(
    question_count: int,
    mix: DifficultyMix | None,
) -> dict[str, int] | None:
    if mix is None:
        return None
    total_mix = mix.easy + mix.medium + mix.hard
    if total_mix == 0:
        return None
    if total_mix == question_count:
        return {"easy": mix.easy, "medium": mix.medium, "hard": mix.hard}

    raw = {
        "easy": (mix.easy / total_mix) * question_count,
        "medium": (mix.medium / total_mix) * question_count,
        "hard": (mix.hard / total_mix) * question_count,
    }
    floored = {k: int(v) for k, v in raw.items()}
    remainder = question_count - sum(floored.values())
    order = sorted(raw.keys(), key=lambda k: raw[k] - floored[k], reverse=True)
    for k in order[:remainder]:
        floored[k] += 1
    return floored


def _select_questions(
    pool: list[tuple[Question, str | None, list[QuestionOption]]],
    *,
    question_count: int,
    difficulty_mix: DifficultyMix | None,
    shuffle_questions: bool,
) -> list[tuple[Question, str | None, list[QuestionOption]]]:
    candidates = list(pool)
    if shuffle_questions:
        random.shuffle(candidates)

    targets = _allocate_difficulty_targets(question_count, difficulty_mix)
    selected: list[tuple[Question, str | None, list[QuestionOption]]] = []
    used_ids: set[UUID] = set()

    if targets is not None:
        by_diff: dict[str, list[tuple[Question, str | None, list[QuestionOption]]]] = defaultdict(
            list
        )
        for item in candidates:
            by_diff[item[0].difficulty].append(item)

        for diff in ("easy", "medium", "hard"):
            needed = targets.get(diff, 0)
            for item in by_diff.get(diff, [])[:needed]:
                selected.append(item)
                used_ids.add(item[0].id)

    # Top up remaining slots from unused candidates (preserves exact count if pool >= count)
    if len(selected) < question_count:
        for item in candidates:
            if item[0].id not in used_ids:
                selected.append(item)
                used_ids.add(item[0].id)
                if len(selected) >= question_count:
                    break

    # Keep passage_group_id items contiguous regardless of shuffling
    if shuffle_questions:
        groups: dict[str, list[tuple[Question, str | None, list[QuestionOption]]]] = {}
        group_order: list[str] = []
        for item in selected:
            q = item[0]
            group_key = f"passage:{q.passage_group_id}" if q.passage_group_id else f"q:{q.id}"
            if group_key not in groups:
                groups[group_key] = []
                group_order.append(group_key)
            groups[group_key].append(item)
        random.shuffle(group_order)
        flattened: list[tuple[Question, str | None, list[QuestionOption]]] = []
        for g_key in group_order:
            flattened.extend(groups[g_key])
        return flattened

    # Non-shuffled: still group passage items adjacently in order of first appearance
    groups_ordered: dict[str, list[tuple[Question, str | None, list[QuestionOption]]]] = {}
    keys_ordered: list[str] = []
    for item in selected:
        q = item[0]
        group_key = f"passage:{q.passage_group_id}" if q.passage_group_id else f"q:{q.id}"
        if group_key not in groups_ordered:
            groups_ordered[group_key] = []
            keys_ordered.append(group_key)
        groups_ordered[group_key].append(item)
    result: list[tuple[Question, str | None, list[QuestionOption]]] = []
    for g_key in keys_ordered:
        result.extend(groups_ordered[g_key])
    return result


def _build_question_snapshot(
    question: Question,
    topic_name: str | None,
    options: list[QuestionOption],
    *,
    shuffle_options: bool,
) -> dict[str, Any]:
    """Create an immutable JSON snapshot including sealed answer_key metadata."""
    answer_data = question.correct_answer_data or {}
    correct_key = answer_data.get("correct_option_key")

    sorted_opts = sorted(options, key=lambda o: (o.display_order, o.option_key))
    snapshot_options: list[dict[str, Any]] = []
    new_correct_key = correct_key

    if shuffle_options and len(sorted_opts) >= 2:
        original_keys = [opt.option_key for opt in sorted_opts]
        shuffled_opts = list(sorted_opts)
        random.shuffle(shuffled_opts)
        for idx, opt in enumerate(shuffled_opts):
            assigned_key = original_keys[idx]
            if opt.option_key == correct_key:
                new_correct_key = assigned_key
            snapshot_options.append(
                {
                    "key": assigned_key,
                    "text": opt.option_text,
                    "display_order": idx,
                }
            )
    else:
        for idx, opt in enumerate(sorted_opts):
            snapshot_options.append(
                {
                    "key": opt.option_key,
                    "text": opt.option_text,
                    "display_order": idx,
                }
            )

    return {
        "question_id": str(question.id),
        "document_id": str(question.document_id) if question.document_id else None,
        "topic_id": str(question.topic_id) if question.topic_id else None,
        "topic_name": topic_name,
        "subject_code": question.subject_code,
        "question_text": question.question_text,
        "question_type": question.question_type,
        "difficulty": question.difficulty,
        "origin": question.origin,
        "source_page_number": question.source_page_number,
        "supporting_excerpt": question.supporting_excerpt,
        "diagram_asset_id": str(question.diagram_asset_id) if question.diagram_asset_id else None,
        "passage_group_id": str(question.passage_group_id) if question.passage_group_id else None,
        "passage_text": question.passage_text,
        "options": snapshot_options,
        "answer_key": {
            "correct_option_key": new_correct_key,
            "explanation": question.explanation or "",
            "answer_key_provenance": question.answer_key_provenance,
        },
    }


def _to_test_out(
    test: Test,
    *,
    latest_attempt_id: UUID | None = None,
    latest_attempt_status: str | None = None,
) -> TestOut:
    doc_ids: list[UUID] = []
    for raw_id in test.source_document_ids_json or []:
        try:
            doc_ids.append(UUID(str(raw_id)))
        except ValueError:
            continue
    return TestOut(
        id=test.id,
        user_id=test.user_id,
        title=test.title,
        exam_config_id=test.exam_config_id,
        subject_code=test.subject_code,
        source_document_ids=doc_ids,
        settings_json=test.settings_json,
        total_questions=test.total_questions,
        max_score=Decimal(test.max_score).quantize(Decimal("0.01")),
        status=test.status,
        created_at=test.created_at,
        latest_attempt_id=latest_attempt_id,
        latest_attempt_status=latest_attempt_status,
    )


class TestBuilderService:
    """Service for previewing question pools and creating snapshotted tests."""

    def __init__(
        self,
        db: Session,
        *,
        clock: ClockFn = utcnow_clock,
        post_submit_hook: AttemptPostSubmitHook = noop_post_submit_hook,
    ) -> None:
        self._db = db
        self._repo = TestRepository(db)
        self._clock = clock
        self._post_submit_hook = post_submit_hook

    def preview(self, user_id: UUID, payload: TestPreviewRequest) -> TestPreviewResponse:
        """Count matching questions by difficulty and subject before test creation."""
        pool = self._repo.query_candidate_questions(
            user_id,
            document_ids=payload.document_ids,
            subject_codes=payload.subject_codes,
            topic_ids=payload.topic_ids,
            question_ids=payload.question_ids,
            origin_mode=payload.origin_mode,
            include_needs_review=payload.include_needs_review,
        )
        by_difficulty = {"easy": 0, "medium": 0, "hard": 0}
        by_subject: dict[str, int] = defaultdict(int)
        for question, _topic_name, _opts in pool:
            if question.difficulty in by_difficulty:
                by_difficulty[question.difficulty] += 1
            else:
                by_difficulty[question.difficulty] = 1
            by_subject[question.subject_code] += 1

        available = len(pool)
        can_satisfy = available >= payload.question_count
        shortfall_reason = (
            None
            if can_satisfy
            else (
                f"Requested {payload.question_count} questions, but only {available} "
                "matching verified questions are available."
            )
        )
        return TestPreviewResponse(
            available_count=available,
            by_difficulty=by_difficulty,
            by_subject=dict(by_subject),
            can_satisfy=can_satisfy,
            shortfall_reason=shortfall_reason,
        )

    def create_test(self, user_id: UUID, payload: TestCreateRequest) -> TestOut:
        """Build a test and freeze immutable `TestQuestion` snapshots."""
        if payload.exam_config_id is not None and not self._repo.exam_config_exists(
            payload.exam_config_id
        ):
            raise TestBuildValidationError(f"Exam config '{payload.exam_config_id}' not found.")

        pool = self._repo.query_candidate_questions(
            user_id,
            document_ids=payload.document_ids,
            subject_codes=payload.subject_codes,
            topic_ids=payload.topic_ids,
            question_ids=payload.question_ids,
            origin_mode=payload.origin_mode,
            include_needs_review=payload.include_needs_review,
        )
        if len(pool) < payload.question_count:
            raise TestBuildValidationError(
                f"Insufficient matching questions: requested {payload.question_count}, "
                f"found {len(pool)}."
            )

        selected = _select_questions(
            pool,
            question_count=payload.question_count,
            difficulty_mix=payload.difficulty_mix,
            shuffle_questions=payload.shuffle_questions,
        )

        points_per_q = payload.points_per_question.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        neg_points = (
            payload.negative_points.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if payload.negative_marking_enabled
            else Decimal("0.00")
        )
        max_score = (points_per_q * Decimal(len(selected))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        per_question_seconds: int | None = None
        total_duration_seconds: int | None = None
        if payload.timer_mode == "speed_challenge":
            per_question_seconds = payload.per_question_seconds
        elif payload.timer_mode == "exam_simulation":
            total_duration_seconds = payload.total_duration_seconds or (len(selected) * 60)

        subjects_present = {q.subject_code for q, _, _ in selected}
        test_subject = next(iter(subjects_present)) if len(subjects_present) == 1 else None

        doc_ids_set = {str(q.document_id) for q, _, _ in selected if q.document_id is not None}
        if payload.document_ids:
            for d_id in payload.document_ids:
                doc_ids_set.add(str(d_id))

        settings_json: dict[str, Any] = {
            "timer_mode": payload.timer_mode,
            "per_question_seconds": per_question_seconds,
            "total_duration_seconds": total_duration_seconds,
            "auto_advance_on_timeout": payload.auto_advance_on_timeout,
            "points_per_question": str(points_per_q),
            "negative_marking_enabled": payload.negative_marking_enabled,
            "negative_points": str(neg_points),
            "shuffle_questions": payload.shuffle_questions,
            "shuffle_options": payload.shuffle_options,
            "show_explanation_after": payload.show_explanation_after,
            "hints_enabled": payload.hints_enabled,
            "origin_mode": payload.origin_mode,
            "include_needs_review": payload.include_needs_review,
        }

        test = Test(
            user_id=user_id,
            title=payload.title.strip(),
            exam_config_id=payload.exam_config_id,
            subject_code=test_subject,
            source_document_ids_json=sorted(doc_ids_set),
            settings_json=settings_json,
            total_questions=len(selected),
            max_score=max_score,
            status="ready",
        )

        test_questions: list[TestQuestion] = []
        for idx, (question, topic_name, options) in enumerate(selected):
            snapshot = _build_question_snapshot(
                question,
                topic_name,
                options,
                shuffle_options=payload.shuffle_options,
            )
            test_questions.append(
                TestQuestion(
                    question_id=question.id,
                    display_order=idx,
                    points=points_per_q,
                    negative_points=neg_points,
                    time_limit_seconds=per_question_seconds,
                    section_code=question.subject_code,
                    passage_group_id=question.passage_group_id,
                    question_snapshot_json=snapshot,
                )
            )

        created = self._repo.create_test_with_questions(test, test_questions)
        return _to_test_out(created)

    def list_tests(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> TestListResponse:
        """List tests owned by `user_id` with latest attempt status."""
        AttemptEngine(
            self._db, clock=self._clock, post_submit_hook=self._post_submit_hook
        ).reconcile_expired_exam_attempts(user_id)
        tests, total = self._repo.list_for_user(user_id, limit=limit, offset=offset)
        latest_map = self._repo.get_latest_attempts_map([t.id for t in tests], user_id)
        items = []
        for t in tests:
            latest = latest_map.get(t.id)
            items.append(
                _to_test_out(
                    t,
                    latest_attempt_id=latest.id if latest else None,
                    latest_attempt_status=latest.status if latest else None,
                )
            )
        return TestListResponse(items=items, total=total, limit=limit, offset=offset)

    def get_test(self, test_id: UUID, user_id: UUID) -> TestOut:
        """Return TestOut for an owned test (without answer keys)."""
        test = self._repo.get_by_id(test_id)
        if test is None:
            raise TestNotFoundError(f"Test '{test_id}' not found")
        if test.user_id != user_id:
            raise TestAccessDeniedError("You do not have access to this test")
        AttemptEngine(
            self._db, clock=self._clock, post_submit_hook=self._post_submit_hook
        ).reconcile_expired_exam_attempts(user_id)
        latest_map = self._repo.get_latest_attempts_map([test.id], user_id)
        latest = latest_map.get(test.id)
        return _to_test_out(
            test,
            latest_attempt_id=latest.id if latest else None,
            latest_attempt_status=latest.status if latest else None,
        )
