from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.provider import LLMProvider
from app.models.assessment import Attempt
from app.models.performance import ImprovementPlan
from app.repositories.performance_repo import PerformanceRepository
from app.schemas.performance import (
    AICoachingSummaryOut,
    ImprovementPlanOut,
    ImprovementPlanRequest,
    RuleRecommendationOut,
    TargetedPracticePreset,
)
from app.services.performance.ai_coach import AICoachService
from app.services.performance.metrics_calculator import (
    FAST_GUESS_THRESHOLD_MS,
    MIN_TOPIC_SAMPLE_SIZE,
    compute_attempt_topic_stats,
    detect_speed_accuracy_anomalies,
    resolve_speed_target_ms,
)
from app.services.performance.topic_aggregator import (
    PerformanceAccessDeniedError,
    PerformanceConflictError,
    PerformanceNotFoundError,
)

RULE_ENGINE_VERSION = "v1"


class RulePlannerService:
    """Deterministic rule-based improvement planner per PRODUCT.md Section 4.6."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = PerformanceRepository(db)
        self._ai_coach = AICoachService()

    def _load_submitted_attempt(self, attempt_id: UUID, user_id: UUID) -> Attempt:
        attempt = self._repo.get_attempt(attempt_id)
        if attempt is None:
            raise PerformanceNotFoundError(f"Attempt '{attempt_id}' not found")
        if attempt.user_id != user_id:
            raise PerformanceAccessDeniedError("You do not have access to this attempt")
        if attempt.status == "in_progress":
            raise PerformanceConflictError(
                "ATTEMPT_IN_PROGRESS",
                "Improvement plan cannot be generated until the attempt is submitted.",
            )
        return attempt

    def _build_recommendations(
        self, *, attempt: Attempt, user_id: UUID
    ) -> list[RuleRecommendationOut]:
        pairs = self._repo.list_attempt_responses(attempt.id)
        aggregates = compute_attempt_topic_stats(attempt=attempt, pairs=pairs)
        anomalies = detect_speed_accuracy_anomalies(attempt=attempt, pairs=pairs)
        speed_target_ms = resolve_speed_target_ms(attempt)

        topic_ids = [agg.topic_id for agg in aggregates if agg.topic_id is not None]
        notes = self._repo.list_notes_for_topics(user_id, topic_ids)
        notes_by_topic: dict[UUID, list[UUID]] = {}
        strategy_notes_by_topic: dict[UUID, list[UUID]] = {}
        for note in notes:
            if note.topic_id is None:
                continue
            notes_by_topic.setdefault(note.topic_id, []).append(note.id)
            if note.note_type in ("strategy_sheet", "quick_revision", "formula_sheet"):
                strategy_notes_by_topic.setdefault(note.topic_id, []).append(note.id)

        recommendations: list[RuleRecommendationOut] = []

        for agg in aggregates:
            cum_tp = (
                self._repo.get_topic_performance(user_id, agg.topic_id)
                if agg.topic_id is not None
                else None
            )
            sample_size = (
                cum_tp.question_count
                if cum_tp is not None and cum_tp.question_count >= agg.question_count
                else agg.question_count
            )
            answered_count = (
                cum_tp.answered_count
                if cum_tp is not None and cum_tp.question_count >= agg.question_count
                else agg.answered_count
            )
            accuracy = (
                Decimal(cum_tp.accuracy_percent)
                if cum_tp is not None
                and cum_tp.question_count >= agg.question_count
                and cum_tp.answered_count > 0
                else agg.accuracy_percent
            )
            avg_time_ms = (
                int(cum_tp.average_time_ms)
                if cum_tp is not None and cum_tp.question_count >= agg.question_count
                else agg.average_time_ms
            )
            note_ids = notes_by_topic.get(agg.topic_id, []) if agg.topic_id else []
            strat_ids = strategy_notes_by_topic.get(agg.topic_id, []) if agg.topic_id else []

            if sample_size < MIN_TOPIC_SAMPLE_SIZE or answered_count == 0 or accuracy is None:
                recommendations.append(
                    RuleRecommendationOut(
                        rule_id="RULE_INSUFFICIENT_DATA",
                        topic_id=agg.topic_id,
                        topic_name=agg.topic_name,
                        subject_code=agg.subject_code,
                        priority=4,
                        action_type="collect_more_data",
                        cited_metrics={
                            "question_count": sample_size,
                            "min_required": MIN_TOPIC_SAMPLE_SIZE,
                            "answered_count": answered_count,
                        },
                        observation=(
                            f"{agg.topic_name} currently has {sample_size} recorded question(s), "
                            f"below the {MIN_TOPIC_SAMPLE_SIZE}-question minimum."
                        ),
                        possible_interpretation=(
                            "This sample is too small to classify the topic reliably as strong "
                            "or weak."
                        ),
                        recommendation=(
                            f"Attempt at least {MIN_TOPIC_SAMPLE_SIZE - sample_size} more "
                            f"question(s) in {agg.topic_name} before treating this as a firm "
                            "weakness."
                        ),
                        recommended_note_ids=note_ids,
                        targeted_practice_preset=(
                            TargetedPracticePreset(
                                topic_ids=[agg.topic_id],
                                question_count=max(5, MIN_TOPIC_SAMPLE_SIZE),
                                difficulty_progression="mixed",
                                timer_mode="learning_mode",
                            )
                            if agg.topic_id is not None
                            else None
                        ),
                    )
                )
                continue

            if accuracy < Decimal("50.00"):
                recommendations.append(
                    RuleRecommendationOut(
                        rule_id="RULE_CONCEPT_REVISION",
                        topic_id=agg.topic_id,
                        topic_name=agg.topic_name,
                        subject_code=agg.subject_code,
                        priority=1,
                        action_type="concept_revision",
                        cited_metrics={
                            "accuracy_percent": str(accuracy),
                            "question_count": sample_size,
                            "answered_count": answered_count,
                            "average_time_ms": avg_time_ms,
                        },
                        observation=(
                            f"Observed {accuracy}% accuracy across {sample_size} question(s) "
                            f"in {agg.topic_name} (below 50%)."
                        ),
                        possible_interpretation=(
                            "Accuracy below 50% with at least 5 attempts may indicate core "
                            "concept or rule gaps."
                        ),
                        recommendation=(
                            f"Revise detailed smart notes for {agg.topic_name} and start an "
                            "easy-to-medium practice set in Learning Mode."
                        ),
                        recommended_note_ids=note_ids,
                        targeted_practice_preset=(
                            TargetedPracticePreset(
                                topic_ids=[agg.topic_id],
                                question_count=10,
                                difficulty_progression="easy_to_medium",
                                timer_mode="learning_mode",
                            )
                            if agg.topic_id is not None
                            else None
                        ),
                    )
                )
            elif accuracy <= Decimal("75.00"):
                recommendations.append(
                    RuleRecommendationOut(
                        rule_id="RULE_MEDIUM_PRACTICE",
                        topic_id=agg.topic_id,
                        topic_name=agg.topic_name,
                        subject_code=agg.subject_code,
                        priority=2,
                        action_type="worked_examples_and_medium_practice",
                        cited_metrics={
                            "accuracy_percent": str(accuracy),
                            "question_count": sample_size,
                            "answered_count": answered_count,
                            "average_time_ms": avg_time_ms,
                        },
                        observation=(
                            f"Observed {accuracy}% accuracy across {sample_size} question(s) "
                            f"in {agg.topic_name} (within 50%-75%)."
                        ),
                        possible_interpretation=(
                            "Foundational understanding may be present, with errors on "
                            "variations or medium-difficulty traps."
                        ),
                        recommendation=(
                            f"Review worked examples for {agg.topic_name} and complete a "
                            "10-question medium practice set."
                        ),
                        recommended_note_ids=note_ids,
                        targeted_practice_preset=(
                            TargetedPracticePreset(
                                topic_ids=[agg.topic_id],
                                question_count=10,
                                difficulty_progression="mixed",
                                timer_mode="learning_mode",
                            )
                            if agg.topic_id is not None
                            else None
                        ),
                    )
                )
            elif avg_time_ms > speed_target_ms:
                avg_sec = round(avg_time_ms / 1000.0, 1)
                target_sec = round(speed_target_ms / 1000.0, 1)
                recommendations.append(
                    RuleRecommendationOut(
                        rule_id="RULE_SPEED_DRILL",
                        topic_id=agg.topic_id,
                        topic_name=agg.topic_name,
                        subject_code=agg.subject_code,
                        priority=2,
                        action_type="speed_drills",
                        cited_metrics={
                            "accuracy_percent": str(accuracy),
                            "question_count": sample_size,
                            "average_time_ms": avg_time_ms,
                            "average_time_seconds": avg_sec,
                            "speed_target_seconds": target_sec,
                        },
                        observation=(
                            f"Observed {accuracy}% accuracy in {agg.topic_name} (above 75%), "
                            f"with average solving time of {avg_sec}s (target {target_sec}s)."
                        ),
                        possible_interpretation=(
                            "Concepts appear solid, while lengthy solving methods may be "
                            "costing time."
                        ),
                        recommendation=(
                            f"Review shortcut/strategy notes for {agg.topic_name} and run a "
                            "35s Speed Challenge drill."
                        ),
                        recommended_note_ids=strat_ids or note_ids,
                        targeted_practice_preset=(
                            TargetedPracticePreset(
                                topic_ids=[agg.topic_id],
                                question_count=10,
                                difficulty_progression="mixed",
                                timer_mode="speed_challenge",
                                per_question_seconds=35,
                            )
                            if agg.topic_id is not None
                            else None
                        ),
                    )
                )

        # Attempt-wide timeout rule
        total_q = len(pairs)
        timeout_ratio = (attempt.timed_out_count / total_q) if total_q > 0 else 0.0
        if attempt.timed_out_count >= 3 or (total_q > 0 and timeout_ratio >= 0.20):
            ratio_pct = round(timeout_ratio * 100.0, 1)
            recommendations.append(
                RuleRecommendationOut(
                    rule_id="RULE_TIMEOUT_MANAGEMENT",
                    topic_id=None,
                    topic_name=None,
                    subject_code=None,
                    priority=1,
                    action_type="shorter_timed_sets_and_question_selection",
                    cited_metrics={
                        "timed_out_count": attempt.timed_out_count,
                        "total_questions": total_q,
                        "timeout_ratio_percent": ratio_pct,
                    },
                    observation=(
                        f"Observed {attempt.timed_out_count} timeout(s) out of {total_q} "
                        f"question(s) ({ratio_pct}%)."
                    ),
                    possible_interpretation=(
                        "Timeouts may reflect spending too long on difficult items instead of "
                        "skipping and returning."
                    ),
                    recommendation=(
                        "Practice shorter timed sets and skip questions that stall beyond 20s "
                        "before returning."
                    ),
                    recommended_note_ids=[],
                    targeted_practice_preset=(
                        TargetedPracticePreset(
                            topic_ids=topic_ids[:3],
                            question_count=min(10, max(5, len(topic_ids) * 3)),
                            difficulty_progression="easy_to_medium",
                            timer_mode="speed_challenge",
                            per_question_seconds=35,
                        )
                        if topic_ids
                        else None
                    ),
                )
            )

        # Fast-incorrect anomaly rule
        fast_err_count = len(anomalies.fast_incorrect_questions)
        if fast_err_count >= 2:
            recommendations.append(
                RuleRecommendationOut(
                    rule_id="RULE_RUSHED_ERRORS",
                    topic_id=None,
                    topic_name=None,
                    subject_code=None,
                    priority=2,
                    action_type="worked_examples_and_medium_practice",
                    cited_metrics={
                        "fast_incorrect_count": fast_err_count,
                        "fast_threshold_seconds": FAST_GUESS_THRESHOLD_MS // 1000,
                    },
                    observation=(
                        f"Observed {fast_err_count} incorrect response(s) submitted in under "
                        f"{FAST_GUESS_THRESHOLD_MS // 1000}s."
                    ),
                    possible_interpretation=(
                        "This may indicate rushed reading or low-confidence guessing under "
                        "time pressure."
                    ),
                    recommendation=(
                        "Run an accuracy-first Learning Mode drill and compare accuracy "
                        "against timed attempts."
                    ),
                    recommended_note_ids=[],
                    targeted_practice_preset=None,
                )
            )

        recommendations.sort(key=lambda r: (r.priority, r.rule_id))
        return recommendations

    def _to_plan_out(self, plan: ImprovementPlan) -> ImprovementPlanOut:
        plan_json: dict[str, Any] = plan.plan_json or {}
        raw_recs = plan_json.get("recommendations") or []
        recs = [RuleRecommendationOut.model_validate(r) for r in raw_recs]

        coaching_data = plan.coaching_text_json or {}
        if coaching_data:
            coaching = AICoachingSummaryOut(
                status=plan.ai_coaching_status,  # type: ignore[arg-type]
                summary_text=str(coaching_data.get("summary_text") or ""),
                topic_explanations=coaching_data.get("topic_explanations") or [],
                model_name=plan.model_name,
                prompt_version=plan.prompt_version,
                grounded_only=True,
            )
        else:
            coaching = AICoachingSummaryOut(
                status=plan.ai_coaching_status,  # type: ignore[arg-type]
                summary_text="Plain-language coaching was not requested.",
                topic_explanations=[],
                model_name=plan.model_name,
                prompt_version=plan.prompt_version,
                grounded_only=True,
            )

        return ImprovementPlanOut(
            id=plan.id,
            attempt_id=plan.attempt_id,
            plan_version=plan.plan_version,
            rule_engine_version=plan.rule_engine_version,
            recommendations=recs,
            ai_coaching=coaching,
            created_at=plan.created_at,
        )

    def get_saved_plan(self, *, attempt_id: UUID, user_id: UUID) -> ImprovementPlanOut:
        self._load_submitted_attempt(attempt_id, user_id)
        existing = self._repo.get_latest_improvement_plan(attempt_id, user_id)
        if existing is None:
            raise PerformanceNotFoundError(
                f"Improvement plan for attempt '{attempt_id}' has not been generated yet"
            )
        return self._to_plan_out(existing)

    def get_or_create_plan(
        self,
        *,
        attempt_id: UUID,
        user_id: UUID,
        payload: ImprovementPlanRequest,
        llm_provider: LLMProvider | None = None,
    ) -> ImprovementPlanOut:
        """Return existing improvement plan or compute and persist a new version."""
        attempt = self._load_submitted_attempt(attempt_id, user_id)
        existing = self._repo.get_latest_improvement_plan(attempt_id, user_id)

        if existing is not None and not payload.force_regenerate:
            if not payload.include_ai_coaching or existing.ai_coaching_status == "generated":
                return self._to_plan_out(existing)

        recommendations = self._build_recommendations(attempt=attempt, user_id=user_id)
        coaching, prompt_name = self._ai_coach.generate_coaching(
            attempt=attempt,
            recommendations=recommendations,
            include_ai_coaching=payload.include_ai_coaching,
            llm_provider=llm_provider,
        )

        next_version = (existing.plan_version + 1) if existing is not None else 1
        plan = ImprovementPlan(
            user_id=user_id,
            attempt_id=attempt.id,
            plan_version=next_version,
            rule_engine_version=RULE_ENGINE_VERSION,
            plan_json={
                "recommendations": [r.model_dump(mode="json") for r in recommendations],
            },
            ai_coaching_status=coaching.status,
            coaching_text_json={
                "summary_text": coaching.summary_text,
                "topic_explanations": [
                    t.model_dump(mode="json") for t in coaching.topic_explanations
                ],
            },
            model_name=coaching.model_name,
            prompt_name=prompt_name,
            prompt_version=coaching.prompt_version,
        )
        self._repo.add(plan)
        self._repo.commit()
        return self._to_plan_out(plan)
