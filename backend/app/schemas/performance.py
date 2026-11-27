from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.test import TestOut

TopicClassificationStatus = Literal[
    "strong",
    "needs_practice",
    "developing",
    "insufficient_data",
]

ErrorCategory = Literal[
    "concept_gap",
    "rule_formula_recall",
    "calculation_error",
    "reading_interpretation",
    "method_selection",
    "time_pressure_timeout",
    "guess_low_confidence",
    "not_attempted",
    "answer_key_source_ambiguity",
]

ActionType = Literal[
    "concept_revision",
    "worked_examples_and_medium_practice",
    "speed_drills",
    "shorter_timed_sets_and_question_selection",
    "collect_more_data",
]


class AnomalyQuestionOut(BaseModel):
    """Observed speed/accuracy anomaly for a single response without diagnostic overclaiming."""

    response_id: UUID
    test_question_id: UUID
    question_id: UUID | None = None
    display_order: int
    topic_id: UUID | None = None
    topic_name: str | None = None
    subject_code: str
    question_text: str
    status: str
    is_correct: bool | None = None
    time_spent_ms: int
    expected_baseline_ms: int
    is_outlier_capped: bool = False
    observation: str
    possible_interpretation: str
    recommendation: str


class SpeedAccuracyAnomaliesOut(BaseModel):
    """Grouped speed and accuracy anomalies for an attempt."""

    slow_questions: list[AnomalyQuestionOut] = Field(default_factory=list)
    fast_incorrect_questions: list[AnomalyQuestionOut] = Field(default_factory=list)
    outlier_latency_count: int = 0
    summary_observation: str
    summary_interpretation: str


class ErrorPatternOut(BaseModel):
    """Evidence-backed tentative mistake pattern summary."""

    error_category: ErrorCategory
    count: int
    question_ids: list[UUID] = Field(default_factory=list)
    test_question_ids: list[UUID] = Field(default_factory=list)
    observation: str
    possible_interpretation: str
    evidence_signals: list[str] = Field(default_factory=list)
    is_tentative: bool = True


class TopicClassificationOut(BaseModel):
    """Per-topic performance classification for an attempt or cumulative profile."""

    topic_id: UUID | None = None
    topic_name: str
    subject_code: str
    status: TopicClassificationStatus
    sample_size: int
    min_required: int = 5
    accuracy_percent: Decimal | None = None
    average_time_ms: int = 0
    median_time_ms: int = 0
    timed_out_count: int = 0
    skipped_count: int = 0


class TopicAttemptDeltaOut(BaseModel):
    """Cross-attempt comparison delta for a topic."""

    topic_id: UUID
    topic_name: str
    subject_code: str
    previous_attempt_id: UUID | None = None
    current_accuracy_percent: Decimal
    previous_accuracy_percent: Decimal | None = None
    accuracy_delta_percent: Decimal | None = None
    current_average_time_ms: int
    previous_average_time_ms: int | None = None
    average_time_delta_ms: int | None = None


class AttemptAnalysisOut(BaseModel):
    """Post-submission analytics report for a single graded attempt."""

    attempt_id: UUID
    test_id: UUID
    speed_accuracy_anomalies: SpeedAccuracyAnomaliesOut
    error_patterns: list[ErrorPatternOut] = Field(default_factory=list)
    topic_classifications: list[TopicClassificationOut] = Field(default_factory=list)
    comparison_to_previous: list[TopicAttemptDeltaOut] = Field(default_factory=list)


class TargetedPracticePreset(BaseModel):
    """Recommended configuration to launch targeted practice from a rule recommendation."""

    topic_ids: list[UUID]
    question_count: int = 10
    difficulty_progression: Literal["easy_to_medium", "mixed"] = "easy_to_medium"
    timer_mode: Literal["speed_challenge", "learning_mode"] = "learning_mode"
    per_question_seconds: int = 35


class RuleRecommendationOut(BaseModel):
    """Deterministic, metric-cited improvement recommendation."""

    rule_id: str
    topic_id: UUID | None = None
    topic_name: str | None = None
    subject_code: str | None = None
    priority: int
    action_type: ActionType
    cited_metrics: dict[str, Any] = Field(default_factory=dict)
    observation: str
    possible_interpretation: str
    recommendation: str
    recommended_note_ids: list[UUID] = Field(default_factory=list)
    targeted_practice_preset: TargetedPracticePreset | None = None


class AICoachingTopicExplanation(BaseModel):
    """Plain-language explanation for a single topic strictly grounded in metrics."""

    topic_name: str
    explanation: str


class AICoachingLLMOutput(BaseModel):
    """Structured schema expected from LLMProvider for plain-language coaching."""

    summary_text: str
    topic_explanations: list[AICoachingTopicExplanation] = Field(default_factory=list)


class AICoachingSummaryOut(BaseModel):
    """Coaching narrative envelope with grounding and model/prompt provenance."""

    status: Literal["not_requested", "generated", "fallback", "failed"]
    summary_text: str
    topic_explanations: list[AICoachingTopicExplanation] = Field(default_factory=list)
    model_name: str | None = None
    prompt_version: str | None = None
    grounded_only: bool = True


class ImprovementPlanRequest(BaseModel):
    """Request body for generating or retrieving an improvement plan."""

    include_ai_coaching: bool = True
    force_regenerate: bool = False


class ImprovementPlanOut(BaseModel):
    """Persisted rule-based improvement plan with optional grounded AI coaching."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    plan_version: int
    rule_engine_version: str
    recommendations: list[RuleRecommendationOut]
    ai_coaching: AICoachingSummaryOut
    created_at: datetime


class TopicPerformanceOut(BaseModel):
    """Cumulative user performance summary for a single topic."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic_id: UUID
    topic_name: str
    subject_code: str
    attempt_count: int
    question_count: int
    answered_count: int
    correct_count: int
    timed_out_count: int
    skipped_count: int
    accuracy_percent: Decimal
    average_time_ms: int
    classification_status: TopicClassificationStatus
    min_required: int = 5
    latest_attempt_id: UUID | None = None
    previous_accuracy_percent: Decimal | None = None
    previous_average_time_ms: int | None = None
    accuracy_delta_percent: Decimal | None = None
    average_time_delta_ms: int | None = None
    updated_at: datetime


class TopicPerformanceListResponse(BaseModel):
    """List response for `/api/v1/performance/topics`."""

    items: list[TopicPerformanceOut]
    total: int


class RevisionItemOut(BaseModel):
    """Revision queue item for weak or developing topics."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic_id: UUID
    topic_name: str
    subject_code: str
    source_attempt_id: UUID | None = None
    reason_rule_id: str
    priority: int
    due_at: datetime
    status: str
    completed_at: datetime | None = None
    created_at: datetime


class RevisionListResponse(BaseModel):
    """List response for `/api/v1/performance/revisions`."""

    items: list[RevisionItemOut]
    total: int


class RevisionUpdateRequest(BaseModel):
    """Status update payload for a revision schedule item."""

    status: Literal["completed", "dismissed"]


class PerformanceOverviewOut(BaseModel):
    """Cross-attempt performance dashboard overview (Screen 10)."""

    total_attempts: int
    overall_accuracy_percent: Decimal | None = None
    overall_avg_time_ms: int = 0
    strong_topics: list[TopicPerformanceOut] = Field(default_factory=list)
    weak_topics: list[TopicPerformanceOut] = Field(default_factory=list)
    developing_topics: list[TopicPerformanceOut] = Field(default_factory=list)
    insufficient_data_topics: list[TopicPerformanceOut] = Field(default_factory=list)
    recent_improvement_deltas: list[TopicAttemptDeltaOut] = Field(default_factory=list)
    due_revisions: list[RevisionItemOut] = Field(default_factory=list)


class TopicTrendPointOut(BaseModel):
    """Single attempt data point in a topic's accuracy/speed trend series."""

    attempt_id: UUID
    test_title: str
    submitted_at: datetime
    question_count: int
    answered_count: int
    correct_count: int
    timed_out_count: int
    accuracy_percent: Decimal
    average_time_ms: int


class LinkedNoteRefOut(BaseModel):
    """Reference to a study note supporting weak-topic revision."""

    id: UUID
    title: str
    note_type: str
    document_id: UUID


class TopicTrendsOut(BaseModel):
    """Cross-attempt trend series and linked study notes for a topic."""

    topic_id: UUID
    topic_name: str
    subject_code: str
    classification_status: TopicClassificationStatus
    question_count: int
    min_required: int = 5
    points: list[TopicTrendPointOut] = Field(default_factory=list)
    recommended_notes: list[LinkedNoteRefOut] = Field(default_factory=list)


class TargetedPracticeRequest(BaseModel):
    """Request payload to create a targeted practice test from weak topics."""

    topic_ids: list[UUID] = Field(min_length=1)
    source_attempt_id: UUID | None = None
    question_count: int = Field(default=10, ge=1, le=100)
    difficulty_progression: Literal["easy_to_medium", "mixed"] = "easy_to_medium"
    timer_mode: Literal["speed_challenge", "learning_mode"] = "learning_mode"
    per_question_seconds: int = Field(default=35, ge=5, le=600)


class TargetedPracticeResponse(BaseModel):
    """Created targeted practice test and supporting revision note IDs."""

    test: TestOut
    linked_note_ids: list[UUID] = Field(default_factory=list)
