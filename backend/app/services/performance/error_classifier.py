from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from app.models.assessment import Attempt, Response, TestQuestion
from app.models.performance import AttemptErrorClassification
from app.schemas.performance import ErrorCategory, ErrorPatternOut
from app.services.performance.metrics_calculator import (
    FAST_GUESS_THRESHOLD_MS,
    compute_slow_threshold_ms,
)


@dataclass(slots=True)
class _ClassifiedItem:
    response: Response
    test_question: TestQuestion
    topic_id: UUID | None
    question_id: UUID | None
    category: ErrorCategory
    confidence_level: str
    observation: str
    possible_interpretation: str
    evidence_signals: list[str]


def _classify_single_response(
    *,
    response: Response,
    tq: TestQuestion,
    slow_threshold_ms: int,
) -> _ClassifiedItem | None:
    if response.status == "answered" and response.is_correct is True:
        return None

    snap = tq.question_snapshot_json or {}
    answer_key = snap.get("answer_key") or {}
    subject_code = str(snap.get("subject_code") or "unknown")
    topic_id_raw = snap.get("topic_id")
    topic_id = UUID(str(topic_id_raw)) if topic_id_raw else None
    q_id_raw = snap.get("question_id")
    question_id = tq.question_id or (UUID(str(q_id_raw)) if q_id_raw else None)

    raw_ms = max(0, int(response.time_spent_ms or 0))
    sec_str = f"{round(raw_ms / 1000.0, 1)}s"
    validation_status = str(snap.get("validation_status") or "verified")
    provenance = str(answer_key.get("answer_key_provenance") or "")
    mistake_tag = response.mistake_reason_self_report
    conf_tag = response.confidence_self_report

    signals: list[str] = []

    if validation_status == "needs_review" or provenance == "unverified":
        signals.append(f"validation_status:{validation_status}")
        if provenance:
            signals.append(f"answer_key_provenance:{provenance}")
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category="answer_key_source_ambiguity",
            confidence_level="tentative",
            observation=(
                f"Question #{tq.display_order + 1} was marked incorrect or unverified, and its "
                "source key is flagged for review."
            ),
            possible_interpretation=(
                "The discrepancy may stem from source answer-key ambiguity rather than a "
                "student concept gap."
            ),
            evidence_signals=signals,
        )

    if response.status == "timed_out":
        signals.append("response_status:timed_out")
        if mistake_tag:
            signals.append(f"self_report:{mistake_tag}")
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category="time_pressure_timeout",
            confidence_level="observed",
            observation=f"Question #{tq.display_order + 1} timed out before an answer was saved.",
            possible_interpretation=(
                "This may indicate time pressure, a slow solving route, or spending too long "
                "on earlier items."
            ),
            evidence_signals=signals,
        )

    if response.status == "skipped":
        signals.append("response_status:skipped")
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category="not_attempted",
            confidence_level="observed",
            observation=(
                f"Question #{tq.display_order + 1} was skipped without selecting an option."
            ),
            possible_interpretation=(
                "Skipping may reflect strategic time management or unfamiliarity with the item."
            ),
            evidence_signals=signals,
        )

    # Answered incorrectly
    signals.append("response_status:answered_incorrect")
    if conf_tag:
        signals.append(f"confidence_self_report:{conf_tag}")
    if mistake_tag:
        signals.append(f"mistake_self_report:{mistake_tag}")

    if mistake_tag == "guessed" or conf_tag == "guessed":
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category="guess_low_confidence",
            confidence_level="student_tagged",
            observation=(
                f"Question #{tq.display_order + 1} was answered incorrectly in {sec_str} and "
                "tagged as a guess."
            ),
            possible_interpretation=(
                "Low confidence or guesswork likely contributed; consider skipping uncertain "
                "items when negative marking is enabled."
            ),
            evidence_signals=signals,
        )

    if mistake_tag == "misread_question":
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category="reading_interpretation",
            confidence_level="student_tagged",
            observation=(
                f"Question #{tq.display_order + 1} was answered incorrectly in {sec_str} and "
                "tagged as a reading mistake."
            ),
            possible_interpretation=(
                "Key constraints, units, or negation words in the stem may have been missed."
            ),
            evidence_signals=signals,
        )

    if mistake_tag == "did_not_understand_concept":
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category="concept_gap",
            confidence_level="student_tagged",
            observation=(
                f"Question #{tq.display_order + 1} was answered incorrectly and tagged as "
                "not understanding the concept."
            ),
            possible_interpretation=(
                "Revising the underlying concept notes and worked examples may help before "
                "timed practice."
            ),
            evidence_signals=signals,
        )

    if mistake_tag == "time_pressure":
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category="time_pressure_timeout",
            confidence_level="student_tagged",
            observation=(
                f"Question #{tq.display_order + 1} was answered incorrectly in {sec_str} and "
                "tagged as time pressure."
            ),
            possible_interpretation=(
                "Time constraints may have prevented checking the steps or reading carefully."
            ),
            evidence_signals=signals,
        )

    if mistake_tag == "knew_method_made_mistake":
        cat: ErrorCategory = (
            "calculation_error"
            if subject_code == "quantitative_aptitude"
            else "rule_formula_recall"
        )
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category=cat,
            confidence_level="student_tagged",
            observation=(
                f"Question #{tq.display_order + 1} was answered incorrectly in {sec_str}; "
                "student noted knowing the method."
            ),
            possible_interpretation=(
                "This may point to an arithmetic slip, sign error, or incomplete formula recall."
            ),
            evidence_signals=signals,
        )

    # Heuristic fallback when no self-report tag exists (strictly tentative)
    if raw_ms < FAST_GUESS_THRESHOLD_MS:
        signals.append(f"time_spent_lt_{FAST_GUESS_THRESHOLD_MS}ms")
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category="guess_low_confidence",
            confidence_level="tentative",
            observation=f"Question #{tq.display_order + 1} was answered incorrectly in {sec_str}.",
            possible_interpretation=(
                "A fast incorrect response may indicate rushed reading or a low-confidence guess."
            ),
            evidence_signals=signals,
        )

    if raw_ms >= slow_threshold_ms:
        signals.append(f"time_spent_gte_{slow_threshold_ms}ms")
        slow_cat: ErrorCategory = (
            "method_selection"
            if subject_code in ("quantitative_aptitude", "reasoning")
            else "concept_gap"
        )
        return _ClassifiedItem(
            response=response,
            test_question=tq,
            topic_id=topic_id,
            question_id=question_id,
            category=slow_cat,
            confidence_level="tentative",
            observation=(
                f"Question #{tq.display_order + 1} was answered incorrectly after {sec_str}."
            ),
            possible_interpretation=(
                "High solving time ending in an error may suggest a suboptimal solving method "
                "or partial concept recall."
            ),
            evidence_signals=signals,
        )

    signals.append("standard_time_incorrect")
    default_cat: ErrorCategory = (
        "rule_formula_recall" if subject_code == "english" else "concept_gap"
    )
    return _ClassifiedItem(
        response=response,
        test_question=tq,
        topic_id=topic_id,
        question_id=question_id,
        category=default_cat,
        confidence_level="tentative",
        observation=f"Question #{tq.display_order + 1} was answered incorrectly in {sec_str}.",
        possible_interpretation=(
            "Without a self-report tag, this may reflect a concept gap, rule recall slip, or "
            "trap distractor."
        ),
        evidence_signals=signals,
    )


class ErrorClassifierService:
    """Evidence-based tentative mistake classifier separating observation from diagnosis."""

    def classify_attempt(
        self,
        *,
        attempt: Attempt,
        pairs: list[tuple[Response, TestQuestion]],
    ) -> tuple[list[AttemptErrorClassification], list[ErrorPatternOut]]:
        """Produce DB classification records and grouped tentative error patterns."""
        slow_threshold_ms = compute_slow_threshold_ms(attempt, pairs)
        classified: list[_ClassifiedItem] = []

        for resp, tq in pairs:
            item = _classify_single_response(
                response=resp, tq=tq, slow_threshold_ms=slow_threshold_ms
            )
            if item is not None:
                classified.append(item)

        db_records = [
            AttemptErrorClassification(
                attempt_id=attempt.id,
                response_id=item.response.id,
                topic_id=item.topic_id,
                error_category=item.category,
                confidence_level=item.confidence_level,
                observation_text=item.observation,
                possible_interpretation_text=item.possible_interpretation,
                evidence_json={"signals": item.evidence_signals},
            )
            for item in classified
        ]

        grouped: dict[ErrorCategory, list[_ClassifiedItem]] = defaultdict(list)
        for item in classified:
            grouped[item.category].append(item)

        patterns: list[ErrorPatternOut] = []
        for category, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
            q_ids = [i.question_id for i in items if i.question_id is not None]
            tq_ids = [i.test_question.id for i in items]
            signals_ordered: list[str] = []
            seen_signals: set[str] = set()
            for item in items:
                for sig in item.evidence_signals:
                    if sig not in seen_signals:
                        seen_signals.add(sig)
                        signals_ordered.append(sig)

            obs = (
                f"Observed {len(items)} question(s) matching '{category.replace('_', ' ')}' "
                f"signals."
            )
            interp = items[0].possible_interpretation
            patterns.append(
                ErrorPatternOut(
                    error_category=category,
                    count=len(items),
                    question_ids=q_ids,
                    test_question_ids=tq_ids,
                    observation=obs,
                    possible_interpretation=interp,
                    evidence_signals=signals_ordered,
                    is_tentative=True,
                )
            )

        return db_records, patterns
