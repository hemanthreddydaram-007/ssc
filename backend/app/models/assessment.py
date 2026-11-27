from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONVariant, UTCDateTime, utcnow


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_subject_topic_status", "subject_code", "topic_id", "validation_status"),
        Index("ix_questions_stem_hash", "stem_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True
    )
    exam_config_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exam_configs.id", ondelete="SET NULL"), nullable=True
    )
    subject_code: Mapped[str] = mapped_column(String(64), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), nullable=False, default="single_choice")
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="extracted")
    source_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supporting_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagram_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_assets.id", ondelete="SET NULL"), nullable=True
    )
    passage_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    passage_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pyq_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    stem_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correct_answer_data: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, nullable=False, default=dict
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answer_key_provenance: Mapped[str] = mapped_column(
        String(64), nullable=False, default="unverified"
    )
    validation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="needs_review"
    )
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class QuestionOption(Base):
    """Public question choices. Deliberately excludes any `is_correct` flag."""

    __tablename__ = "question_options"
    __table_args__ = (UniqueConstraint("question_id", "option_key", name="uq_question_option_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    option_key: Mapped[str] = mapped_column(String(8), nullable=False)
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    exam_config_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exam_configs.id", ondelete="SET NULL"), nullable=True
    )
    subject_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_document_ids_json: Mapped[list[Any]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("0.00")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class TestQuestion(Base):
    __tablename__ = "test_questions"
    __table_args__ = (UniqueConstraint("test_id", "display_order", name="uq_test_display_order"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=Decimal("1.00"))
    negative_points: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("0.00")
    )
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    passage_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    question_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, nullable=False, default=dict
    )


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (Index("ix_attempts_user_status", "user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    timer_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress")
    current_question_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    total_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_question_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    max_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("0.00")
    )
    total_time_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timed_out_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Response(Base):
    __tablename__ = "responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "test_question_id", name="uq_attempt_test_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False
    )
    test_question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("test_questions.id", ondelete="CASCADE"), nullable=False
    )
    selected_answer_json: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    graded_points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    time_spent_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    shown_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    question_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_resumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_marked_for_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unvisited")
    confidence_self_report: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mistake_reason_self_report: Mapped[str | None] = mapped_column(String(64), nullable=True)
