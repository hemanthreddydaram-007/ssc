from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from uuid import UUID

from app.models.assessment import Attempt, Response, TestQuestion
from app.schemas.performance import (
    AnomalyQuestionOut,
    SpeedAccuracyAnomaliesOut,
    TopicClassificationOut,
    TopicClassificationStatus,
)

MIN_TOPIC_SAMPLE_SIZE = 5
FAST_GUESS_THRESHOLD_MS = 10_000
DEFAULT_TOPIC_SPEED_TARGET_MS = 45_000
OUTLIER_LATENCY_CAP_MS = 300_000
SLOW_MULTIPLIER = 1.75


@dataclass(slots=True)
class TopicAttemptAggregate:
    """Intermediate per-topic stats computed from one attempt's responses."""

    topic_id: UUID | None
    topic_name: str
    subject_code: str
    question_count: int
    answered_count: int
    correct_count: int
    incorrect_count: int
    skipped_count: int
    timed_out_count: int
    accuracy_percent: Decimal | None
    average_time_ms: int
    median_time_ms: int
    classification_status: TopicClassificationStatus
    outlier_count: int


def compute_accuracy_percent(correct_count: int, answered_count: int) -> Decimal | None:
    """Compute Decimal percentage `(correct / answered) * 100`, or None if 0 answered."""
    if answered_count <= 0:
        return None
    return ((Decimal(correct_count) * Decimal("100")) / Decimal(answered_count)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def cap_latency_ms(raw_ms: int) -> tuple[int, bool]:
    """Bound extreme idle/tab-background latencies so averages are not skewed."""
    ms = max(0, int(raw_ms or 0))
    if ms > OUTLIER_LATENCY_CAP_MS:
        return OUTLIER_LATENCY_CAP_MS, True
    return ms, False


def resolve_speed_target_ms(attempt: Attempt | None = None) -> int:
    """Return expected per-question solving speed target in milliseconds."""
    if attempt is not None and attempt.timer_mode == "speed_challenge":
        if attempt.per_question_seconds and attempt.per_question_seconds > 0:
            return attempt.per_question_seconds * 1000
        return 35_000
    return DEFAULT_TOPIC_SPEED_TARGET_MS


def classify_topic_status(
    *,
    question_count: int,
    answered_count: int,
    accuracy_percent: Decimal | None,
    average_time_ms: int,
    speed_target_ms: int = DEFAULT_TOPIC_SPEED_TARGET_MS,
) -> TopicClassificationStatus:
    """Classify a topic strictly respecting the minimum 5-question sample threshold."""
    if question_count < MIN_TOPIC_SAMPLE_SIZE or answered_count <= 0 or accuracy_percent is None:
        return "insufficient_data"
    if accuracy_percent < Decimal("50.00"):
        return "needs_practice"
    if accuracy_percent <= Decimal("75.00"):
        return "developing"
    if average_time_ms > speed_target_ms:
        return "developing"
    return "strong"


def _extract_topic_id(snap: dict) -> UUID | None:
    raw = snap.get("topic_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def compute_attempt_topic_stats(
    *,
    attempt: Attempt,
    pairs: list[tuple[Response, TestQuestion]],
) -> list[TopicAttemptAggregate]:
    """Aggregate accuracy, winsorized speed, and status per topic for one attempt."""
    speed_target_ms = resolve_speed_target_ms(attempt)
    grouped: dict[str, list[tuple[Response, TestQuestion]]] = defaultdict(list)
    meta: dict[str, tuple[UUID | None, str, str]] = {}

    for resp, tq in pairs:
        snap = tq.question_snapshot_json or {}
        topic_id = _extract_topic_id(snap)
        topic_name = str(snap.get("topic_name") or "General / Unassigned")
        subject_code = str(snap.get("subject_code") or tq.section_code or "unknown")
        key = f"{topic_id or 'none'}::{subject_code}::{topic_name}"
        grouped[key].append((resp, tq))
        meta[key] = (topic_id, topic_name, subject_code)

    results: list[TopicAttemptAggregate] = []
    for key, items in grouped.items():
        topic_id, topic_name, subject_code = meta[key]
        question_count = len(items)
        answered_count = 0
        correct_count = 0
        incorrect_count = 0
        skipped_count = 0
        timed_out_count = 0
        answered_times: list[int] = []
        outlier_count = 0

        for resp, _tq in items:
            if resp.status == "answered":
                answered_count += 1
                if resp.is_correct:
                    correct_count += 1
                else:
                    incorrect_count += 1
                capped_ms, is_outlier = cap_latency_ms(resp.time_spent_ms)
                answered_times.append(capped_ms)
                if is_outlier:
                    outlier_count += 1
            elif resp.status == "timed_out":
                timed_out_count += 1
            else:
                skipped_count += 1

        avg_ms = round(sum(answered_times) / len(answered_times)) if answered_times else 0
        med_ms = round(median(answered_times)) if answered_times else 0
        acc = compute_accuracy_percent(correct_count, answered_count)
        status = classify_topic_status(
            question_count=question_count,
            answered_count=answered_count,
            accuracy_percent=acc,
            average_time_ms=avg_ms,
            speed_target_ms=speed_target_ms,
        )
        results.append(
            TopicAttemptAggregate(
                topic_id=topic_id,
                topic_name=topic_name,
                subject_code=subject_code,
                question_count=question_count,
                answered_count=answered_count,
                correct_count=correct_count,
                incorrect_count=incorrect_count,
                skipped_count=skipped_count,
                timed_out_count=timed_out_count,
                accuracy_percent=acc,
                average_time_ms=avg_ms,
                median_time_ms=med_ms,
                classification_status=status,
                outlier_count=outlier_count,
            )
        )

    return results


def to_topic_classifications_out(
    aggregates: list[TopicAttemptAggregate],
) -> list[TopicClassificationOut]:
    """Convert internal topic aggregates into API classification items."""
    return [
        TopicClassificationOut(
            topic_id=agg.topic_id,
            topic_name=agg.topic_name,
            subject_code=agg.subject_code,
            status=agg.classification_status,
            sample_size=agg.question_count,
            min_required=MIN_TOPIC_SAMPLE_SIZE,
            accuracy_percent=agg.accuracy_percent,
            average_time_ms=agg.average_time_ms,
            median_time_ms=agg.median_time_ms,
            timed_out_count=agg.timed_out_count,
            skipped_count=agg.skipped_count,
        )
        for agg in aggregates
    ]


def compute_slow_threshold_ms(
    attempt: Attempt,
    pairs: list[tuple[Response, TestQuestion]],
) -> int:
    """Compute attempt-aware threshold above which a question is flagged as unusually slow."""
    if attempt.timer_mode == "speed_challenge":
        target = resolve_speed_target_ms(attempt)
        return max(25_000, int(target * 0.85))

    answered_times = [
        cap_latency_ms(resp.time_spent_ms)[0]
        for resp, _ in pairs
        if resp.status == "answered"
    ]
    if answered_times:
        med = median(answered_times)
        baseline = max(20_000, min(60_000, int(med)))
    else:
        baseline = DEFAULT_TOPIC_SPEED_TARGET_MS
    return max(DEFAULT_TOPIC_SPEED_TARGET_MS, int(baseline * SLOW_MULTIPLIER))


def detect_speed_accuracy_anomalies(
    *,
    attempt: Attempt,
    pairs: list[tuple[Response, TestQuestion]],
) -> SpeedAccuracyAnomaliesOut:
    """Detect slow responses and fast-incorrect responses with hedged wording."""
    slow_threshold_ms = compute_slow_threshold_ms(attempt, pairs)
    baseline_ms = resolve_speed_target_ms(attempt)
    slow_questions: list[AnomalyQuestionOut] = []
    fast_incorrect_questions: list[AnomalyQuestionOut] = []
    outlier_latency_count = 0

    for resp, tq in pairs:
        if resp.status != "answered":
            continue

        snap = tq.question_snapshot_json or {}
        topic_id = _extract_topic_id(snap)
        q_id_str = snap.get("question_id")
        question_id = tq.question_id or (UUID(str(q_id_str)) if q_id_str else None)
        raw_ms = max(0, int(resp.time_spent_ms or 0))
        capped_ms, is_outlier = cap_latency_ms(raw_ms)
        if is_outlier:
            outlier_latency_count += 1

        sec_display = round(capped_ms / 1000.0, 1)
        raw_sec_display = round(raw_ms / 1000.0, 1)

        if raw_ms >= slow_threshold_ms:
            if is_outlier:
                obs = (
                    f"Question #{tq.display_order + 1} recorded {raw_sec_display}s "
                    f"(capped at {OUTLIER_LATENCY_CAP_MS // 1000}s for speed averages)."
                )
                interp = (
                    "This may reflect prolonged difficulty or leaving the browser tab idle "
                    "during an untimed/total-timer section."
                )
            else:
                obs = (
                    f"You spent {sec_display}s on question #{tq.display_order + 1} "
                    f"(threshold {round(slow_threshold_ms / 1000.0, 1)}s)."
                )
                interp = (
                    "This may indicate an unfamiliar method, lengthy calculation, or "
                    "hesitation between options."
                )
            slow_questions.append(
                AnomalyQuestionOut(
                    response_id=resp.id,
                    test_question_id=tq.id,
                    question_id=question_id,
                    display_order=tq.display_order,
                    topic_id=topic_id,
                    topic_name=snap.get("topic_name"),
                    subject_code=str(snap.get("subject_code") or "unknown"),
                    question_text=str(snap.get("question_text") or ""),
                    status=resp.status,
                    is_correct=resp.is_correct,
                    time_spent_ms=capped_ms,
                    expected_baseline_ms=baseline_ms,
                    is_outlier_capped=is_outlier,
                    observation=obs,
                    possible_interpretation=interp,
                    recommendation=(
                        "Review the faster solving method or shortcut sheet for this topic "
                        "and practice skipping time-heavy items earlier."
                    ),
                )
            )

        if resp.is_correct is False and raw_ms < FAST_GUESS_THRESHOLD_MS:
            fast_incorrect_questions.append(
                AnomalyQuestionOut(
                    response_id=resp.id,
                    test_question_id=tq.id,
                    question_id=question_id,
                    display_order=tq.display_order,
                    topic_id=topic_id,
                    topic_name=snap.get("topic_name"),
                    subject_code=str(snap.get("subject_code") or "unknown"),
                    question_text=str(snap.get("question_text") or ""),
                    status=resp.status,
                    is_correct=resp.is_correct,
                    time_spent_ms=raw_ms,
                    expected_baseline_ms=baseline_ms,
                    is_outlier_capped=False,
                    observation=(
                        f"You answered question #{tq.display_order + 1} incorrectly in "
                        f"{round(raw_ms / 1000.0, 1)}s (under {FAST_GUESS_THRESHOLD_MS // 1000}s)."
                    ),
                    possible_interpretation=(
                        "This may indicate rushed reading, a trap option, or a quick guess."
                    ),
                    recommendation=(
                        "Try an accuracy-first practice set in Learning Mode and compare "
                        "whether slowing down changes accuracy."
                    ),
                )
            )

    summary_obs = (
        f"Observed {len(slow_questions)} slow response(s) and "
        f"{len(fast_incorrect_questions)} fast incorrect response(s) under "
        f"{FAST_GUESS_THRESHOLD_MS // 1000}s."
    )
    if outlier_latency_count > 0:
        summary_obs += (
            f" {outlier_latency_count} response(s) exceeded 300s and were capped in "
            "speed averages to limit idle-tab skew."
        )

    if fast_incorrect_questions or slow_questions:
        summary_interp = (
            "Timing patterns alone cannot confirm root causes, but fast errors may suggest "
            "rushed reading or guessing while slow responses may suggest method friction."
        )
    else:
        summary_interp = (
            "No extreme speed outliers were observed relative to the attempt baseline."
        )

    return SpeedAccuracyAnomaliesOut(
        slow_questions=slow_questions,
        fast_incorrect_questions=fast_incorrect_questions,
        outlier_latency_count=outlier_latency_count,
        summary_observation=summary_obs,
        summary_interpretation=summary_interp,
    )
