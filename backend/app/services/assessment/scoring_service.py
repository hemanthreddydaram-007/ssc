from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.assessment import Attempt, Response, Test, TestQuestion
from app.schemas.attempt import (
    AttemptResultsOut,
    DifficultyBreakdownItemOut,
    PlayerOptionOut,
    QuestionReviewOut,
    TopicBreakdownItemOut,
)

AttemptPostSubmitHook = Callable[[Session, UUID], None]


def noop_post_submit_hook(_db: Session, _attempt_id: UUID) -> None:
    """Default M6 no-op post-submit hook (M7 wires TopicAggregator here)."""


def _quantize_score(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _pct(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return ((Decimal(numerator) * Decimal("100")) / Decimal(denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


class ScoringService:
    """Deterministic `Decimal`-precision grader and post-submission results builder."""

    def grade_single_response(
        self,
        *,
        response: Response,
        test_question: TestQuestion,
        negative_marking_enabled: bool,
    ) -> Decimal:
        """Grade a single response deterministically from its immutable snapshot."""
        snapshot = test_question.question_snapshot_json or {}
        answer_key = snapshot.get("answer_key") or {}
        correct_key = answer_key.get("correct_option_key")

        if response.status == "answered" and response.selected_answer_json:
            selected_key = response.selected_answer_json.get("selected_option_key")
            is_correct = bool(correct_key and selected_key == correct_key)
            response.is_correct = is_correct
            if is_correct:
                points = _quantize_score(Decimal(test_question.points))
            elif negative_marking_enabled:
                points = _quantize_score(-Decimal(test_question.negative_points))
            else:
                points = Decimal("0.00")
            response.graded_points = points
            return points

        response.is_correct = None
        response.graded_points = Decimal("0.00")
        return Decimal("0.00")

    def finalize_attempt(
        self,
        *,
        attempt: Attempt,
        test: Test,
        pairs: list[tuple[Response, TestQuestion]],
        submitted_at: datetime,
        timed_out_submission: bool,
    ) -> None:
        """Finalize unvisited responses, grade all items with Decimal, and populate Attempt."""
        settings = test.settings_json or {}
        neg_enabled = bool(settings.get("negative_marking_enabled", False))

        total_score = Decimal("0.00")
        total_time_ms = 0
        correct_count = 0
        incorrect_count = 0
        skipped_count = 0
        timed_out_count = 0

        for response, tq in pairs:
            if response.status == "unvisited":
                response.status = "timed_out" if timed_out_submission else "skipped"
                response.locked_at = submitted_at
            elif (
                response.status in ("answered", "skipped", "timed_out")
                and response.locked_at is None
            ):
                response.locked_at = submitted_at

            if response.status == "answered":
                points = self.grade_single_response(
                    response=response,
                    test_question=tq,
                    negative_marking_enabled=neg_enabled,
                )
                total_score += points
                if response.is_correct:
                    correct_count += 1
                else:
                    incorrect_count += 1
            elif response.status == "timed_out":
                response.is_correct = None
                response.graded_points = Decimal("0.00")
                timed_out_count += 1
            else:
                response.is_correct = None
                response.graded_points = Decimal("0.00")
                skipped_count += 1

            total_time_ms += int(response.time_spent_ms or 0)

        attempt.status = "timed_out_submitted" if timed_out_submission else "submitted"
        attempt.submitted_at = submitted_at
        attempt.total_score = _quantize_score(total_score)
        attempt.total_time_ms = total_time_ms
        attempt.correct_count = correct_count
        attempt.incorrect_count = incorrect_count
        attempt.skipped_count = skipped_count
        attempt.timed_out_count = timed_out_count

    def build_results(
        self,
        *,
        attempt: Attempt,
        test: Test,
        pairs: list[tuple[Response, TestQuestion]],
    ) -> AttemptResultsOut:
        """Build full AttemptResultsOut with topic/difficulty breakdowns and question review."""
        total_questions = len(pairs)
        attempted_total = attempt.correct_count + attempt.incorrect_count
        attempted_time_sum = sum(
            int(r.time_spent_ms or 0) for r, _ in pairs if r.status == "answered"
        )
        avg_time_ms = round(attempted_time_sum / attempted_total) if attempted_total > 0 else 0

        topic_stats: dict[str, dict[str, Any]] = {}
        diff_stats: dict[str, dict[str, Any]] = {}
        review_items: list[QuestionReviewOut] = []

        for response, tq in pairs:
            snap = tq.question_snapshot_json or {}
            answer_key = snap.get("answer_key") or {}
            subject_code = str(snap.get("subject_code") or "unknown")
            topic_id_str = snap.get("topic_id")
            topic_id = UUID(topic_id_str) if topic_id_str else None
            topic_name = str(snap.get("topic_name") or "General / Unassigned")
            difficulty = str(snap.get("difficulty") or "medium")
            selected_key = (
                response.selected_answer_json.get("selected_option_key")
                if response.selected_answer_json
                else None
            )

            t_key = f"{topic_id_str or 'none'}::{subject_code}::{topic_name}"
            if t_key not in topic_stats:
                topic_stats[t_key] = {
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "subject_code": subject_code,
                    "total_questions": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "skipped": 0,
                    "timed_out": 0,
                    "attempted_time_ms": 0,
                }
            ts = topic_stats[t_key]
            ts["total_questions"] += 1
            if response.status == "answered":
                ts["attempted_time_ms"] += int(response.time_spent_ms or 0)
                if response.is_correct:
                    ts["correct"] += 1
                else:
                    ts["incorrect"] += 1
            elif response.status == "timed_out":
                ts["timed_out"] += 1
            else:
                ts["skipped"] += 1

            if difficulty not in diff_stats:
                diff_stats[difficulty] = {
                    "total_questions": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "attempted_time_ms": 0,
                }
            ds = diff_stats[difficulty]
            ds["total_questions"] += 1
            if response.status == "answered":
                ds["attempted_time_ms"] += int(response.time_spent_ms or 0)
                if response.is_correct:
                    ds["correct"] += 1
                else:
                    ds["incorrect"] += 1

            doc_id_str = snap.get("document_id")
            diagram_id_str = snap.get("diagram_asset_id")
            q_id_str = snap.get("question_id")
            options = [
                PlayerOptionOut(
                    key=str(opt.get("key", "")),
                    text=str(opt.get("text", "")),
                    display_order=int(opt.get("display_order", idx)),
                )
                for idx, opt in enumerate(snap.get("options") or [])
            ]

            review_items.append(
                QuestionReviewOut(
                    response_id=response.id,
                    test_question_id=tq.id,
                    question_id=tq.question_id or (UUID(q_id_str) if q_id_str else None),
                    display_order=tq.display_order,
                    subject_code=subject_code,
                    topic_id=topic_id,
                    topic_name=snap.get("topic_name"),
                    difficulty=difficulty,
                    origin=str(snap.get("origin") or "extracted"),
                    question_text=str(snap.get("question_text") or ""),
                    passage_text=snap.get("passage_text"),
                    document_id=UUID(doc_id_str) if doc_id_str else None,
                    source_page_number=snap.get("source_page_number"),
                    supporting_excerpt=snap.get("supporting_excerpt"),
                    diagram_asset_id=UUID(diagram_id_str) if diagram_id_str else None,
                    options=options,
                    selected_option_key=selected_key,
                    correct_option_key=answer_key.get("correct_option_key"),
                    is_correct=response.is_correct,
                    graded_points=_quantize_score(
                        Decimal(response.graded_points)
                        if response.graded_points is not None
                        else Decimal("0.00")
                    ),
                    status=response.status,
                    time_spent_ms=int(response.time_spent_ms or 0),
                    is_marked_for_review=response.is_marked_for_review,
                    explanation=str(answer_key.get("explanation") or ""),
                    answer_key_provenance=str(
                        answer_key.get("answer_key_provenance") or "unverified"
                    ),
                    confidence_self_report=response.confidence_self_report,
                    mistake_reason_self_report=response.mistake_reason_self_report,
                )
            )

        topic_breakdown: list[TopicBreakdownItemOut] = []
        for ts in topic_stats.values():
            t_att = ts["correct"] + ts["incorrect"]
            topic_breakdown.append(
                TopicBreakdownItemOut(
                    topic_id=ts["topic_id"],
                    topic_name=ts["topic_name"],
                    subject_code=ts["subject_code"],
                    total_questions=ts["total_questions"],
                    attempted_count=t_att,
                    correct_count=ts["correct"],
                    incorrect_count=ts["incorrect"],
                    skipped_count=ts["skipped"],
                    timed_out_count=ts["timed_out"],
                    accuracy_percent=_pct(ts["correct"], t_att),
                    average_time_ms=round(ts["attempted_time_ms"] / t_att) if t_att > 0 else 0,
                )
            )

        difficulty_breakdown: list[DifficultyBreakdownItemOut] = []
        ordered_diffs = ["easy", "medium", "hard"] + [
            d for d in diff_stats if d not in ("easy", "medium", "hard")
        ]
        for diff in ordered_diffs:
            if diff not in diff_stats:
                continue
            ds = diff_stats[diff]
            d_att = ds["correct"] + ds["incorrect"]
            difficulty_breakdown.append(
                DifficultyBreakdownItemOut(
                    difficulty=diff,
                    total_questions=ds["total_questions"],
                    attempted_count=d_att,
                    correct_count=ds["correct"],
                    incorrect_count=ds["incorrect"],
                    accuracy_percent=_pct(ds["correct"], d_att),
                    average_time_ms=round(ds["attempted_time_ms"] / d_att) if d_att > 0 else 0,
                )
            )

        # Ensure defaultdict unused import lint doesn't trigger
        _ = defaultdict

        assert attempt.submitted_at is not None
        assert attempt.total_score is not None
        return AttemptResultsOut(
            attempt_id=attempt.id,
            test_id=test.id,
            test_title=test.title,
            timer_mode=attempt.timer_mode,
            status=attempt.status,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            total_score=_quantize_score(Decimal(attempt.total_score)),
            max_score=_quantize_score(Decimal(attempt.max_score)),
            total_time_ms=int(attempt.total_time_ms or 0),
            total_questions=total_questions,
            correct_count=attempt.correct_count,
            incorrect_count=attempt.incorrect_count,
            skipped_count=attempt.skipped_count,
            timed_out_count=attempt.timed_out_count,
            accuracy_attempted_percent=_pct(attempt.correct_count, attempted_total),
            accuracy_overall_percent=_pct(attempt.correct_count, total_questions),
            average_time_ms=avg_time_ms,
            topic_breakdown=topic_breakdown,
            difficulty_breakdown=difficulty_breakdown,
            questions=review_items,
        )
