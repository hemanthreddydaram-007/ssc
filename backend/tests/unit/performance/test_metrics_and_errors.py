from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models.assessment import Attempt, Response, TestQuestion
from app.services.performance.error_classifier import ErrorClassifierService
from app.services.performance.metrics_calculator import (
    OUTLIER_LATENCY_CAP_MS,
    classify_topic_status,
    compute_accuracy_percent,
    compute_attempt_topic_stats,
    detect_speed_accuracy_anomalies,
)


def _make_attempt(
    *,
    timer_mode: str = "exam_simulation",
    per_question_seconds: int | None = None,
) -> Attempt:
    now = datetime.now(UTC)
    return Attempt(
        id=uuid.uuid4(),
        test_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        timer_mode=timer_mode,
        status="submitted",
        started_at=now,
        submitted_at=now,
        per_question_seconds=per_question_seconds,
    )


def _make_pair(
    *,
    attempt_id: uuid.UUID,
    display_order: int,
    topic_id: uuid.UUID | None,
    topic_name: str,
    subject_code: str = "quantitative_aptitude",
    status: str = "answered",
    is_correct: bool | None = True,
    time_spent_ms: int = 20_000,
    validation_status: str = "verified",
    answer_key_provenance: str = "source_answer_key",
    mistake_tag: str | None = None,
    conf_tag: str | None = None,
) -> tuple[Response, TestQuestion]:
    tq = TestQuestion(
        id=uuid.uuid4(),
        test_id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        display_order=display_order,
        points=Decimal("2.00"),
        negative_points=Decimal("0.50"),
        section_code=subject_code,
        question_snapshot_json={
            "question_id": str(uuid.uuid4()),
            "topic_id": str(topic_id) if topic_id else None,
            "topic_name": topic_name,
            "subject_code": subject_code,
            "difficulty": "medium",
            "question_text": f"Sample question {display_order + 1}",
            "validation_status": validation_status,
            "answer_key": {
                "correct_option_key": "A",
                "answer_key_provenance": answer_key_provenance,
            },
        },
    )
    resp = Response(
        id=uuid.uuid4(),
        attempt_id=attempt_id,
        test_question_id=tq.id,
        status=status,
        is_correct=is_correct,
        time_spent_ms=time_spent_ms,
        mistake_reason_self_report=mistake_tag,
        confidence_self_report=conf_tag,
    )
    return resp, tq


def test_compute_accuracy_zero_answered_returns_none() -> None:
    assert compute_accuracy_percent(0, 0) is None
    assert compute_accuracy_percent(3, 4) == Decimal("75.00")


def test_classify_topic_status_thresholds() -> None:
    assert (
        classify_topic_status(
            question_count=4,
            answered_count=4,
            accuracy_percent=Decimal("100.00"),
            average_time_ms=10_000,
        )
        == "insufficient_data"
    )
    assert (
        classify_topic_status(
            question_count=5,
            answered_count=5,
            accuracy_percent=Decimal("40.00"),
            average_time_ms=20_000,
        )
        == "needs_practice"
    )
    assert (
        classify_topic_status(
            question_count=5,
            answered_count=5,
            accuracy_percent=Decimal("60.00"),
            average_time_ms=20_000,
        )
        == "developing"
    )
    assert (
        classify_topic_status(
            question_count=5,
            answered_count=5,
            accuracy_percent=Decimal("80.00"),
            average_time_ms=60_000,
            speed_target_ms=45_000,
        )
        == "developing"
    )
    assert (
        classify_topic_status(
            question_count=5,
            answered_count=5,
            accuracy_percent=Decimal("80.00"),
            average_time_ms=25_000,
            speed_target_ms=45_000,
        )
        == "strong"
    )


def test_outlier_latency_capped_and_anomalies_distinguish_observation_from_diagnosis() -> None:
    attempt = _make_attempt(timer_mode="exam_simulation")
    topic_id = uuid.uuid4()
    pairs = [
        _make_pair(
            attempt_id=attempt.id,
            display_order=0,
            topic_id=topic_id,
            topic_name="Percentages",
            is_correct=False,
            time_spent_ms=4_500,  # fast incorrect
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=1,
            topic_id=topic_id,
            topic_name="Percentages",
            is_correct=True,
            time_spent_ms=900_000,  # idle-tab 15 min outlier
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=2,
            topic_id=topic_id,
            topic_name="Percentages",
            status="skipped",
            is_correct=None,
            time_spent_ms=0,
        ),
    ]

    aggs = compute_attempt_topic_stats(attempt=attempt, pairs=pairs)
    assert len(aggs) == 1
    agg = aggs[0]
    assert agg.question_count == 3
    assert agg.answered_count == 2
    assert agg.skipped_count == 1
    assert agg.classification_status == "insufficient_data"
    # Average uses capped 300_000ms instead of 900_000ms, excluding skipped 0ms
    assert agg.average_time_ms == round((4_500 + OUTLIER_LATENCY_CAP_MS) / 2)

    anomalies = detect_speed_accuracy_anomalies(attempt=attempt, pairs=pairs)
    assert anomalies.outlier_latency_count == 1
    assert len(anomalies.slow_questions) == 1
    assert anomalies.slow_questions[0].is_outlier_capped is True
    assert "capped" in anomalies.slow_questions[0].observation.lower()
    assert "may" in anomalies.slow_questions[0].possible_interpretation.lower()

    assert len(anomalies.fast_incorrect_questions) == 1
    assert "4.5s" in anomalies.fast_incorrect_questions[0].observation
    assert "may indicate" in anomalies.fast_incorrect_questions[0].possible_interpretation.lower()


def test_error_classifier_covers_evidence_and_self_reports() -> None:
    attempt = _make_attempt(timer_mode="speed_challenge", per_question_seconds=35)
    topic_id = uuid.uuid4()
    pairs = [
        _make_pair(
            attempt_id=attempt.id,
            display_order=0,
            topic_id=topic_id,
            topic_name="Algebra",
            is_correct=False,
            validation_status="needs_review",
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=1,
            topic_id=topic_id,
            topic_name="Algebra",
            status="timed_out",
            is_correct=None,
            time_spent_ms=35_000,
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=2,
            topic_id=topic_id,
            topic_name="Algebra",
            status="skipped",
            is_correct=None,
            time_spent_ms=0,
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=3,
            topic_id=topic_id,
            topic_name="Algebra",
            is_correct=False,
            time_spent_ms=18_000,
            mistake_tag="knew_method_made_mistake",
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=4,
            topic_id=topic_id,
            topic_name="Algebra",
            is_correct=False,
            time_spent_ms=5_000,
            mistake_tag="guessed",
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=5,
            topic_id=topic_id,
            topic_name="Algebra",
            subject_code="english",
            is_correct=False,
            time_spent_ms=15_000,
            mistake_tag="misread_question",
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=6,
            topic_id=topic_id,
            topic_name="Algebra",
            is_correct=False,
            time_spent_ms=22_000,
            mistake_tag="did_not_understand_concept",
        ),
        _make_pair(
            attempt_id=attempt.id,
            display_order=7,
            topic_id=topic_id,
            topic_name="Algebra",
            is_correct=False,
            time_spent_ms=32_000,  # slow without tag -> method_selection
        ),
    ]

    db_records, patterns = ErrorClassifierService().classify_attempt(
        attempt=attempt, pairs=pairs
    )
    assert len(db_records) == 8
    categories = {p.error_category for p in patterns}
    assert {
        "answer_key_source_ambiguity",
        "time_pressure_timeout",
        "not_attempted",
        "calculation_error",
        "guess_low_confidence",
        "reading_interpretation",
        "concept_gap",
        "method_selection",
    }.issubset(categories)
    assert all(p.is_tentative is True for p in patterns)
    assert all(p.evidence_signals for p in patterns)
