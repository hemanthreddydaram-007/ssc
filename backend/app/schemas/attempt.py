from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PlayerOptionOut(BaseModel):
    """Active-test option schema (strictly omits any correctness flag)."""

    key: str
    text: str
    display_order: int


class PlayerQuestionOut(BaseModel):
    """Active-test question schema (strictly omits answer keys and explanations)."""

    test_question_id: UUID
    display_order: int
    subject_code: str
    topic_id: UUID | None = None
    topic_name: str | None = None
    question_text: str
    question_type: str
    difficulty: str
    document_id: UUID | None = None
    source_page_number: int | None = None
    diagram_asset_id: UUID | None = None
    passage_group_id: UUID | None = None
    passage_text: str | None = None
    options: list[PlayerOptionOut]
    points: Decimal
    negative_points: Decimal
    time_limit_seconds: int | None = None
    section_code: str | None = None
    selected_option_key: str | None = None
    is_marked_for_review: bool = False
    status: str
    shown_at: datetime | None = None
    question_expires_at: datetime | None = None
    question_remaining_seconds: int | None = None
    time_spent_ms: int = 0
    is_locked: bool = False
    hint: str | None = None


class QuestionPaletteItemOut(BaseModel):
    """Compact status item for the Test Player navigation palette."""

    index: int
    test_question_id: UUID
    status: str
    is_marked_for_review: bool
    selected_option_key: str | None = None
    is_locked: bool = False


class LockedQuestionFeedbackOut(BaseModel):
    """Single-question feedback revealed ONLY for a locked response in learning_mode."""

    response_id: UUID
    test_question_id: UUID
    selected_option_key: str | None = None
    correct_option_key: str | None = None
    is_correct: bool | None = None
    explanation: str = ""
    answer_key_provenance: str
    source_page_number: int | None = None
    supporting_excerpt: str | None = None


class AttemptCurrentOut(BaseModel):
    """Authoritative active-attempt state returned on start, resume, and navigation."""

    attempt_id: UUID
    test_id: UUID
    test_title: str
    status: str
    timer_mode: str
    server_now: datetime
    started_at: datetime
    attempt_expires_at: datetime | None = None
    attempt_remaining_seconds: int | None = None
    current_question_index: int
    total_questions: int
    current_question: PlayerQuestionOut | None = None
    palette: list[QuestionPaletteItemOut]
    settings: dict[str, Any]
    locked_feedback: LockedQuestionFeedbackOut | None = None


class NavigateRequest(BaseModel):
    """Request to move the active question cursor in Exam Simulation or Learning Mode."""

    target_index: int = Field(ge=0)


class SaveResponseRequest(BaseModel):
    """Request to save an answer, skip, or review flag on a test question."""

    test_question_id: UUID
    selected_option_key: str | None = None
    action: Literal["answer", "skip", "mark_review", "unmark_review"] = "answer"
    is_marked_for_review: bool | None = None
    advance: bool = True


class ResponseSaveOut(BaseModel):
    """Response returned after saving an answer or action."""

    response_id: UUID
    attempt_id: UUID
    test_question_id: UUID
    status: str
    selected_option_key: str | None = None
    is_marked_for_review: bool
    is_locked: bool
    time_spent_ms: int
    next_state: AttemptCurrentOut
    locked_feedback: LockedQuestionFeedbackOut | None = None


class SelfReportRequest(BaseModel):
    """Optional student confidence / mistake-reason tag per Section 4.5."""

    confidence_self_report: Literal["high", "medium", "low", "guessed"] | None = None
    mistake_reason_self_report: (
        Literal[
            "guessed",
            "knew_method_made_mistake",
            "did_not_understand_concept",
            "misread_question",
            "time_pressure",
        ]
        | None
    ) = None


class SelfReportOut(BaseModel):
    """Updated self-report tags for a response."""

    response_id: UUID
    attempt_id: UUID
    confidence_self_report: str | None = None
    mistake_reason_self_report: str | None = None


class AttemptSummaryOut(BaseModel):
    """Summary of a test attempt returned on list and submit."""

    attempt_id: UUID
    test_id: UUID
    test_title: str
    timer_mode: str
    status: str
    started_at: datetime
    submitted_at: datetime | None = None
    total_score: Decimal | None = None
    max_score: Decimal
    total_time_ms: int
    total_questions: int
    correct_count: int
    incorrect_count: int
    skipped_count: int
    timed_out_count: int


class AttemptListResponse(BaseModel):
    """Paginated/listed attempts for the current user."""

    items: list[AttemptSummaryOut]
    total: int


class TopicBreakdownItemOut(BaseModel):
    """Per-topic score, accuracy, and speed metrics for a graded attempt."""

    topic_id: UUID | None = None
    topic_name: str
    subject_code: str
    total_questions: int
    attempted_count: int
    correct_count: int
    incorrect_count: int
    skipped_count: int
    timed_out_count: int
    accuracy_percent: Decimal
    average_time_ms: int


class DifficultyBreakdownItemOut(BaseModel):
    """Per-difficulty accuracy and speed metrics for a graded attempt."""

    difficulty: str
    total_questions: int
    attempted_count: int
    correct_count: int
    incorrect_count: int
    accuracy_percent: Decimal
    average_time_ms: int


class QuestionReviewOut(BaseModel):
    """Post-submission review item with answer key, explanation, and provenance."""

    response_id: UUID
    test_question_id: UUID
    question_id: UUID | None = None
    display_order: int
    subject_code: str
    topic_id: UUID | None = None
    topic_name: str | None = None
    difficulty: str
    origin: str
    question_text: str
    passage_text: str | None = None
    document_id: UUID | None = None
    source_page_number: int | None = None
    supporting_excerpt: str | None = None
    diagram_asset_id: UUID | None = None
    options: list[PlayerOptionOut]
    selected_option_key: str | None = None
    correct_option_key: str | None = None
    is_correct: bool | None = None
    graded_points: Decimal
    status: str
    time_spent_ms: int
    is_marked_for_review: bool
    explanation: str
    answer_key_provenance: str
    confidence_self_report: str | None = None
    mistake_reason_self_report: str | None = None


class AttemptResultsOut(BaseModel):
    """Full graded results report (exposed only after attempt submission)."""

    attempt_id: UUID
    test_id: UUID
    test_title: str
    timer_mode: str
    status: str
    started_at: datetime
    submitted_at: datetime
    total_score: Decimal
    max_score: Decimal
    total_time_ms: int
    total_questions: int
    correct_count: int
    incorrect_count: int
    skipped_count: int
    timed_out_count: int
    accuracy_attempted_percent: Decimal
    accuracy_overall_percent: Decimal
    average_time_ms: int
    topic_breakdown: list[TopicBreakdownItemOut]
    difficulty_breakdown: list[DifficultyBreakdownItemOut]
    questions: list[QuestionReviewOut]
