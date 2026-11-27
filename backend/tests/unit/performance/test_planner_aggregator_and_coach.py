from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.ai.mock_provider import MockLLMProvider
from app.models.assessment import Attempt, Question, QuestionOption, Response, Test, TestQuestion
from app.models.document import Document
from app.models.learning import Note, Topic
from app.models.performance import RevisionScheduleItem, TopicPerformance, TopicPerformanceSnapshot
from app.models.user import User
from app.schemas.performance import (
    AICoachingLLMOutput,
    AICoachingTopicExplanation,
    ImprovementPlanRequest,
    TargetedPracticeRequest,
)
from app.services.performance.rule_planner import RulePlannerService
from app.services.performance.targeted_practice import (
    TargetedPracticeService,
    TargetedPracticeValidationError,
)
from app.services.performance.topic_aggregator import TopicAggregatorService, on_attempt_submitted


def _seed_user_topics_and_notes(db: Session) -> tuple[User, Topic, Topic, Note]:
    user = User(id=uuid.uuid4(), display_name="Perf Test User")
    db.add(user)
    topic_math = Topic(
        id=uuid.uuid4(),
        subject_code="quantitative_aptitude",
        name="Time and Work",
        slug="time-and-work",
    )
    topic_eng = Topic(
        id=uuid.uuid4(),
        subject_code="english",
        name="Error Spotting",
        slug="error-spotting",
    )
    db.add_all([topic_math, topic_eng])

    doc = Document(
        id=uuid.uuid4(),
        user_id=user.id,
        title="SSC Maths Notes",
        original_filename="maths.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        sha256="a" * 64,
        storage_key="users/test/maths.pdf",
        subject_code="quantitative_aptitude",
        material_type="notes",
        language="en",
        page_count=5,
        status="ready",
    )
    db.add(doc)
    db.flush()

    note = Note(
        id=uuid.uuid4(),
        document_id=doc.id,
        topic_id=topic_math.id,
        subject_code="quantitative_aptitude",
        note_type="detailed",
        title="Time and Work Smart Notes",
        content_json={"sections": []},
        status="ready",
    )
    db.add(note)
    db.commit()
    return user, topic_math, topic_eng, note


def _create_submitted_attempt(
    db: Session,
    *,
    user_id: uuid.UUID,
    topic: Topic,
    outcomes: list[tuple[str, bool | None, int]],
    submitted_at: datetime,
    timer_mode: str = "exam_simulation",
    per_question_seconds: int | None = None,
) -> Attempt:
    test = Test(
        id=uuid.uuid4(),
        user_id=user_id,
        title=f"Practice {topic.name}",
        subject_code=topic.subject_code,
        settings_json={"timer_mode": timer_mode},
        total_questions=len(outcomes),
        max_score=Decimal(len(outcomes) * 2),
        status="ready",
    )
    db.add(test)
    db.flush()

    correct_c = sum(1 for st, ok, _ in outcomes if st == "answered" and ok)
    incorrect_c = sum(1 for st, ok, _ in outcomes if st == "answered" and ok is False)
    skipped_c = sum(1 for st, _, _ in outcomes if st == "skipped")
    timed_out_c = sum(1 for st, _, _ in outcomes if st == "timed_out")

    attempt = Attempt(
        id=uuid.uuid4(),
        test_id=test.id,
        user_id=user_id,
        timer_mode=timer_mode,
        status="submitted",
        started_at=submitted_at - timedelta(minutes=5),
        submitted_at=submitted_at,
        per_question_seconds=per_question_seconds,
        total_score=Decimal(correct_c * 2),
        max_score=Decimal(len(outcomes) * 2),
        correct_count=correct_c,
        incorrect_count=incorrect_c,
        skipped_count=skipped_c,
        timed_out_count=timed_out_c,
    )
    db.add(attempt)
    db.flush()

    for idx, (st, ok, ms) in enumerate(outcomes):
        tq = TestQuestion(
            id=uuid.uuid4(),
            test_id=test.id,
            display_order=idx,
            points=Decimal("2.00"),
            negative_points=Decimal("0.00"),
            section_code=topic.subject_code,
            question_snapshot_json={
                "question_id": str(uuid.uuid4()),
                "topic_id": str(topic.id),
                "topic_name": topic.name,
                "subject_code": topic.subject_code,
                "difficulty": "medium",
                "question_text": f"Q{idx + 1}",
                "validation_status": "verified",
                "answer_key": {
                    "correct_option_key": "A",
                    "answer_key_provenance": "source_answer_key",
                },
            },
        )
        db.add(tq)
        db.flush()
        resp = Response(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            test_question_id=tq.id,
            status=st,
            is_correct=ok,
            time_spent_ms=ms,
        )
        db.add(resp)

    db.commit()
    return attempt


def test_topic_aggregator_idempotent_and_cross_attempt_trends(db_session: Session) -> None:
    user, topic_math, _topic_eng, _note = _seed_user_topics_and_notes(db_session)
    t1 = datetime.now(UTC) - timedelta(days=2)
    t2 = datetime.now(UTC) - timedelta(days=1)

    # Attempt 1: 5 questions, 1/5 = 20% -> needs_practice
    a1 = _create_submitted_attempt(
        db_session,
        user_id=user.id,
        topic=topic_math,
        outcomes=[
            ("answered", True, 20_000),
            ("answered", False, 25_000),
            ("answered", False, 25_000),
            ("answered", False, 30_000),
            ("timed_out", None, 35_000),
        ],
        submitted_at=t1,
    )
    on_attempt_submitted(db_session, a1.id)
    # Re-run with Attempt object to verify idempotency (no duplicate snapshot or double-count)
    on_attempt_submitted(db_session, a1)

    tp = db_session.query(TopicPerformance).filter_by(user_id=user.id, topic_id=topic_math.id).one()
    assert tp.attempt_count == 1
    assert tp.question_count == 5
    assert tp.answered_count == 4
    assert tp.correct_count == 1
    assert tp.accuracy_percent == Decimal("25.00")
    assert tp.classification_status == "needs_practice"

    snaps = db_session.query(TopicPerformanceSnapshot).filter_by(attempt_id=a1.id).all()
    assert len(snaps) == 1

    revs = db_session.query(RevisionScheduleItem).filter_by(user_id=user.id, status="due").all()
    assert len(revs) == 1

    # Attempt 2: 5/5 correct, fast (15s) -> cumulative improves from 25% to 66.67% (developing)
    a2 = _create_submitted_attempt(
        db_session,
        user_id=user.id,
        topic=topic_math,
        outcomes=[("answered", True, 15_000)] * 5,
        submitted_at=t2,
    )
    on_attempt_submitted(db_session, a2.id)

    db_session.refresh(tp)
    assert tp.attempt_count == 2
    assert tp.question_count == 10
    assert tp.previous_accuracy_percent == Decimal("25.00")
    assert tp.accuracy_percent == Decimal("66.67")
    assert tp.classification_status == "developing"

    service = TopicAggregatorService(db_session)
    analysis = service.analyze_attempt(attempt_id=a2.id, user_id=user.id)
    assert len(analysis.comparison_to_previous) == 1
    delta = analysis.comparison_to_previous[0]
    assert delta.previous_attempt_id == a1.id
    assert delta.accuracy_delta_percent == Decimal("75.00")

    trends = service.get_topic_trends(user_id=user.id, topic_id=topic_math.id)
    assert len(trends.points) == 2
    assert len(trends.recommended_notes) == 1


def test_rule_planner_and_ai_coach_grounding_fallback(db_session: Session) -> None:
    user, topic_math, _topic_eng, note = _seed_user_topics_and_notes(db_session)
    now = datetime.now(UTC)

    # 5 questions, 1/5 answered = 20% + 3 timeouts -> triggers CONCEPT_REVISION & TIMEOUT_MANAGEMENT
    attempt = _create_submitted_attempt(
        db_session,
        user_id=user.id,
        topic=topic_math,
        outcomes=[
            ("answered", True, 20_000),
            ("answered", False, 20_000),
            ("answered", False, 20_000),
            ("answered", False, 20_000),
            ("answered", False, 20_000),
        ],
        submitted_at=now,
    )
    attempt.timed_out_count = 3
    db_session.commit()
    on_attempt_submitted(db_session, attempt.id)

    # Case 1: LLM fabricates number 99.9 -> must reject and fall back cleanly
    bad_mock = MockLLMProvider()
    bad_mock.enqueue_raw(
        AICoachingLLMOutput(
            summary_text="You achieved 99.9% overall and missed 42 items.",
            topic_explanations=[
                AICoachingTopicExplanation(
                    topic_name="Time and Work",
                    explanation="Your score dropped by 99.9%.",
                )
            ],
        ).model_dump_json(),
        prompt_name="performance_coaching",
    )

    planner = RulePlannerService(db_session)
    plan_fallback = planner.get_or_create_plan(
        attempt_id=attempt.id,
        user_id=user.id,
        payload=ImprovementPlanRequest(include_ai_coaching=True),
        llm_provider=bad_mock,
    )
    rule_ids = {r.rule_id for r in plan_fallback.recommendations}
    assert "RULE_CONCEPT_REVISION" in rule_ids
    assert "RULE_TIMEOUT_MANAGEMENT" in rule_ids
    concept_rec = next(
        r for r in plan_fallback.recommendations if r.rule_id == "RULE_CONCEPT_REVISION"
    )
    assert note.id in concept_rec.recommended_note_ids
    assert plan_fallback.ai_coaching.status == "fallback"
    assert "99.9" not in plan_fallback.ai_coaching.summary_text

    # Case 2: Grounded LLM response citing only real numbers passes validation
    good_mock = MockLLMProvider()
    good_mock.enqueue_raw(
        AICoachingLLMOutput(
            summary_text=(
                "You answered 1 question correctly and 4 incorrectly, with 20.00% accuracy "
                "in Time and Work across 5 questions, plus 3 timed out items."
            ),
            topic_explanations=[
                AICoachingTopicExplanation(
                    topic_name="Time and Work",
                    explanation="Observed 20.00% accuracy over 5 questions; revise smart notes.",
                )
            ],
        ).model_dump_json(),
        prompt_name="performance_coaching",
    )
    plan_ok = planner.get_or_create_plan(
        attempt_id=attempt.id,
        user_id=user.id,
        payload=ImprovementPlanRequest(include_ai_coaching=True, force_regenerate=True),
        llm_provider=good_mock,
    )
    assert plan_ok.plan_version == 2
    assert plan_ok.ai_coaching.status == "generated"
    assert plan_ok.ai_coaching.model_name == "mock-gemini-2.5-flash"


def test_rule_planner_insufficient_data_and_speed_drill_rules(db_session: Session) -> None:
    user, topic_math, topic_eng, _note = _seed_user_topics_and_notes(db_session)
    now = datetime.now(UTC)

    # Fewer than 5 questions in English -> RULE_INSUFFICIENT_DATA
    a_small = _create_submitted_attempt(
        db_session,
        user_id=user.id,
        topic=topic_eng,
        outcomes=[("answered", False, 15_000), ("answered", False, 15_000)],
        submitted_at=now,
    )
    on_attempt_submitted(db_session, a_small.id)
    plan_small = RulePlannerService(db_session).get_or_create_plan(
        attempt_id=a_small.id,
        user_id=user.id,
        payload=ImprovementPlanRequest(include_ai_coaching=False),
    )
    assert len(plan_small.recommendations) == 1
    assert plan_small.recommendations[0].rule_id == "RULE_INSUFFICIENT_DATA"
    assert plan_small.ai_coaching.status == "not_requested"

    # >75% accuracy with high average time (80s > 45s target) -> RULE_SPEED_DRILL
    a_slow_accurate = _create_submitted_attempt(
        db_session,
        user_id=user.id,
        topic=topic_math,
        outcomes=[("answered", True, 80_000)] * 5,
        submitted_at=now,
    )
    on_attempt_submitted(db_session, a_slow_accurate.id)
    plan_speed = RulePlannerService(db_session).get_or_create_plan(
        attempt_id=a_slow_accurate.id,
        user_id=user.id,
        payload=ImprovementPlanRequest(include_ai_coaching=False),
    )
    assert any(r.rule_id == "RULE_SPEED_DRILL" for r in plan_speed.recommendations)


def test_targeted_practice_creates_test_and_links_notes(db_session: Session) -> None:
    user, topic_math, _topic_eng, note = _seed_user_topics_and_notes(db_session)

    # Seed 5 verified questions in topic_math
    for i in range(5):
        q = Question(
            id=uuid.uuid4(),
            document_id=note.document_id,
            topic_id=topic_math.id,
            subject_code="quantitative_aptitude",
            question_text=f"Targeted Q{i + 1}",
            question_type="single_choice",
            difficulty="easy" if i < 3 else "medium",
            origin="generated",
            stem_hash=f"hash-{i}-{uuid.uuid4()}",
            correct_answer_data={"correct_option_key": "A"},
            explanation="Exp",
            answer_key_provenance="deterministic_math",
            validation_status="verified",
        )
        db_session.add(q)
        db_session.flush()
        for idx, key in enumerate(["A", "B", "C", "D"]):
            db_session.add(
                QuestionOption(
                    id=uuid.uuid4(),
                    question_id=q.id,
                    option_key=key,
                    option_text=f"Opt {key} {i}",
                    display_order=idx,
                )
            )
    db_session.commit()

    svc = TargetedPracticeService(db_session)
    res = svc.create_targeted_practice(
        user_id=user.id,
        payload=TargetedPracticeRequest(
            topic_ids=[topic_math.id],
            question_count=5,
            difficulty_progression="easy_to_medium",
            timer_mode="learning_mode",
        ),
    )
    assert res.test.total_questions == 5
    assert note.id in res.linked_note_ids

    with pytest.raises(TargetedPracticeValidationError):
        svc.create_targeted_practice(
            user_id=user.id,
            payload=TargetedPracticeRequest(topic_ids=[topic_math.id], question_count=20),
        )
