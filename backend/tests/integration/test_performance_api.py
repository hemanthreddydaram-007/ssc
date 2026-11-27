"""End-to-end integration tests for Milestone M7: Performance Analysis, Plan & Dashboard.

Covers all 5 verification gates from @coordinator #59:
  1. Post-submit hook idempotency + 409 in-progress guard on /analysis and /improvement-plan.
  2. Hand-calculated metrics (0 answered, skipped 0ms excluded, outlier >300s capped),
     <5 question insufficient_data gate, and >=5 classification buckets.
  3. Observation vs tentative Interpretation separation across speed/accuracy anomalies and
     error categories (time_pressure_timeout, not_attempted, guess_low_confidence,
     calculation_error via self-report, answer_key_source_ambiguity).
  4. Rule-based improvement plan citing metrics + linked_note_ids + grounded AI coaching
     (valid generated vs ungrounded-number fallback) + GET saved plan zero LLM calls.
  5. Multi-attempt trends & deltas, targeted practice (201 & 422), revisions GET/PATCH,
     live /api/v1/dashboard totals, and cross-user 403/isolation enforcement.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.db.session import get_db
from app.models.assessment import Question, QuestionOption
from app.models.document import Document
from app.models.learning import Note, Topic
from app.models.performance import (
    AttemptErrorClassification,
    RevisionScheduleItem,
    TopicPerformance,
    TopicPerformanceSnapshot,
)
from app.services.assessment.timer_service import get_clock

USER_A = "00000000-0000-0000-0000-000000000001"
USER_B = "00000000-0000-0000-0000-000000000002"
AUTH_A = {"X-User-Id": USER_A}
AUTH_B = {"X-User-Id": USER_B}


class MutableClock:
    """Deterministic UTC clock for controlling per-question & attempt elapsed times."""

    def __init__(self, initial: datetime | None = None) -> None:
        self.now = initial or datetime(2026, 11, 27, 14, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: float = 0) -> datetime:
        self.now = self.now + timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def m7_env(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[
    tuple[TestClient, MutableClock, MockLLMProvider, sessionmaker[Session]], None, None
]:
    """Yield (TestClient, MutableClock, MockLLMProvider, SessionLocal)."""
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)
    app = main_module.create_app()
    clock = MutableClock()
    mock_provider = MockLLMProvider()

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider

    with (
        patch(
            "httpx.HTTPTransport.handle_request",
            side_effect=AssertionError("Live HTTP/Gemini call attempted during M7 test!"),
        ),
        patch(
            "httpx.AsyncHTTPTransport.handle_async_request",
            side_effect=AssertionError("Live async HTTP/Gemini call attempted during M7 test!"),
        ),
        TestClient(app) as tc,
    ):
        yield tc, clock, mock_provider, testing_session_local


def _create_topic_with_questions(
    db: Session,
    *,
    subject_code: str,
    topic_name: str,
    count: int,
    user_id: str = USER_A,
    document_id: uuid.UUID | None = None,
    validation_status: str = "verified",
) -> tuple[Topic, list[str]]:
    topic = Topic(
        subject_code=subject_code,
        name=topic_name,
        slug=f"{topic_name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
    )
    db.add(topic)
    db.flush()

    q_ids: list[str] = []
    for idx in range(count):
        q = Question(
            document_id=document_id,
            topic_id=topic.id,
            subject_code=subject_code,
            question_text=f"{topic_name} question #{idx + 1}: compute {idx + 2} * 3?",
            question_type="single_choice",
            difficulty="easy" if idx < 3 else "medium",
            origin="generated",
            source_page_number=1,
            supporting_excerpt=f"{topic_name} rule",
            stem_hash=uuid.uuid4().hex,
            correct_answer_data=(
                {"correct_option_key": "B", "owner_user_id": user_id}
                if document_id is None
                else {"correct_option_key": "B"}
            ),
            explanation="Option B is correct.",
            answer_key_provenance=(
                "source_answer_key" if validation_status == "verified" else "unverified"
            ),
            validation_status=validation_status,
        )
        db.add(q)
        db.flush()
        for o_idx, key in enumerate(("A", "B", "C", "D")):
            db.add(
                QuestionOption(
                    question_id=q.id,
                    option_key=key,
                    option_text=f"Choice {key}-{idx}",
                    display_order=o_idx,
                )
            )
        q_ids.append(str(q.id))
    return topic, q_ids


# ---------------------------------------------------------------------------
# 1 & 2 & 3. Post-submit hook, 409 guard, hand-calculated metrics, <5 gate, errors
# ---------------------------------------------------------------------------


def test_post_submit_hook_metrics_insufficient_data_gate_and_error_patterns(
    m7_env: tuple[TestClient, MutableClock, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, clock, _, session_factory = m7_env

    with session_factory() as db:
        weak_topic, weak_q_ids = _create_topic_with_questions(
            db, subject_code="quantitative_aptitude", topic_name="Percentages", count=5
        )
        strong_topic, strong_q_ids = _create_topic_with_questions(
            db, subject_code="quantitative_aptitude", topic_name="Ratios", count=5
        )
        small_topic, small_q_ids = _create_topic_with_questions(
            db, subject_code="english", topic_name="Idioms", count=3
        )
        ambig_topic, ambig_q_ids = _create_topic_with_questions(
            db,
            subject_code="general_awareness",
            topic_name="Polity Ambiguity",
            count=1,
            validation_status="needs_review",
        )
        db.commit()
        weak_tid, strong_tid, small_tid = weak_topic.id, strong_topic.id, small_topic.id
        all_q_ids = weak_q_ids + strong_q_ids + small_q_ids + ambig_q_ids

    # Build Speed Challenge test (include_needs_review=True to test answer_key_source_ambiguity)
    test_resp = client.post(
        "/api/v1/tests",
        json={
            "title": "M7 Comprehensive Diagnostic",
            "question_ids": all_q_ids,
            "question_count": len(all_q_ids),
            "timer_mode": "exam_simulation",
            "total_duration_seconds": 1200,
            "include_needs_review": True,
        },
        headers=AUTH_A,
    )
    assert test_resp.status_code == 201, test_resp.text
    test_id = test_resp.json()["id"]

    start = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A).json()
    attempt_id = start["attempt_id"]

    # 1. 409 In-progress guard on /analysis and POST/GET /improvement-plan
    assert client.get(f"/api/v1/attempts/{attempt_id}/analysis", headers=AUTH_A).status_code == 409
    assert (
        client.post(
            f"/api/v1/attempts/{attempt_id}/improvement-plan", json={}, headers=AUTH_A
        ).status_code
        == 409
    )
    assert (
        client.get(f"/api/v1/attempts/{attempt_id}/improvement-plan", headers=AUTH_A).status_code
        == 409
    )

    palette = start["palette"]

    # Map each test_question_id to its intended action/timing
    # Percentages (5 items, indices 0..4):
    #   0: Correct in 20s
    #   1: Incorrect in 4s (fast_incorrect + tagged guessed)
    #   2: Incorrect in 350s (outlier > 300_000ms -> capped to 300_000ms + tagged knew_method)
    #   3: Skipped in 0s (excluded from solving-speed average!)
    #   4: Incorrect in 16s
    # Ratios (5 items, indices 5..9): all 5 Correct in 15s each -> strong (100%, 15s <= 45s)
    # Idioms (3 items, indices 10..12): 3 Incorrect in 10s -> insufficient_data (<5 questions!)
    # Polity Ambiguity (1 item, index 13): Incorrect in 12s -> answer_key_source_ambiguity
    self_report_targets: list[tuple[str, str, str]] = []

    for idx, p_item in enumerate(palette):
        if idx > 0:
            client.post(
                f"/api/v1/attempts/{attempt_id}/navigate",
                json={"target_index": idx},
                headers=AUTH_A,
            )
        tq_id = p_item["test_question_id"]

        if idx == 0:
            clock.advance(seconds=20)
            client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={"test_question_id": tq_id, "selected_option_key": "B", "action": "answer"},
                headers=AUTH_A,
            )
        elif idx == 1:
            clock.advance(seconds=4)
            r = client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={"test_question_id": tq_id, "selected_option_key": "A", "action": "answer"},
                headers=AUTH_A,
            ).json()
            self_report_targets.append((r["response_id"], "guessed", "guessed"))
        elif idx == 2:
            clock.advance(seconds=350)  # outlier latency > 300s
            r = client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={"test_question_id": tq_id, "selected_option_key": "A", "action": "answer"},
                headers=AUTH_A,
            ).json()
            self_report_targets.append(
                (r["response_id"], "medium", "knew_method_made_mistake")
            )
        elif idx == 3:
            # Immediate skip (0s) -> must NOT dilute solving-speed average
            client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={"test_question_id": tq_id, "action": "skip"},
                headers=AUTH_A,
            )
        elif idx == 4:
            clock.advance(seconds=16)
            client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={"test_question_id": tq_id, "selected_option_key": "A", "action": "answer"},
                headers=AUTH_A,
            )
        elif 5 <= idx <= 9:
            clock.advance(seconds=15)
            client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={"test_question_id": tq_id, "selected_option_key": "B", "action": "answer"},
                headers=AUTH_A,
            )
        elif 10 <= idx <= 12:
            clock.advance(seconds=10)
            client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={"test_question_id": tq_id, "selected_option_key": "A", "action": "answer"},
                headers=AUTH_A,
            )
        else:
            clock.advance(seconds=12)
            client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={"test_question_id": tq_id, "selected_option_key": "A", "action": "answer"},
                headers=AUTH_A,
            )

    # Apply self-reports BEFORE submit so post-submit hook classifies them immediately
    for resp_id, conf, reason in self_report_targets:
        client.patch(
            f"/api/v1/attempts/{attempt_id}/responses/{resp_id}/self-report",
            json={"confidence_self_report": conf, "mistake_reason_self_report": reason},
            headers=AUTH_A,
        )

    # Submit + idempotent double submit
    sub1 = client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=AUTH_A)
    sub2 = client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=AUTH_A)
    assert sub1.status_code == 200 and sub2.status_code == 200

    # Verify DB post-submit hook populated snapshots, topic_performance, errors, revisions
    with session_factory() as db:
        snaps = db.execute(
            select(TopicPerformanceSnapshot).where(
                TopicPerformanceSnapshot.attempt_id == uuid.UUID(attempt_id)
            )
        ).scalars().all()
        assert len(snaps) == 4  # 1 snapshot per topic, NOT doubled by double submit
        tp_weak = db.execute(
            select(TopicPerformance).where(
                TopicPerformance.user_id == uuid.UUID(USER_A),
                TopicPerformance.topic_id == weak_tid,
            )
        ).scalar_one()
        assert tp_weak.attempt_count == 1
        assert tp_weak.question_count == 5
        # Percentages: 1 correct / 4 answered = 25.00%; avg_ms = (20000+4000+300000+16000)/4 = 85000
        assert Decimal(tp_weak.accuracy_percent) == Decimal("25.00")
        assert tp_weak.average_time_ms == 85000
        assert tp_weak.classification_status == "needs_practice"

        tp_strong = db.execute(
            select(TopicPerformance).where(
                TopicPerformance.user_id == uuid.UUID(USER_A),
                TopicPerformance.topic_id == strong_tid,
            )
        ).scalar_one()
        assert tp_strong.classification_status == "strong"

        tp_small = db.execute(
            select(TopicPerformance).where(
                TopicPerformance.user_id == uuid.UUID(USER_A),
                TopicPerformance.topic_id == small_tid,
            )
        ).scalar_one()
        # 0% accuracy on 3 questions -> MUST remain insufficient_data (<5 gate!)
        assert tp_small.classification_status == "insufficient_data"

        err_rows = db.execute(
            select(AttemptErrorClassification).where(
                AttemptErrorClassification.attempt_id == uuid.UUID(attempt_id)
            )
        ).scalars().all()
        assert len(err_rows) >= 5

        rev_rows = db.execute(
            select(RevisionScheduleItem).where(
                RevisionScheduleItem.user_id == uuid.UUID(USER_A),
                RevisionScheduleItem.topic_id == weak_tid,
            )
        ).scalars().all()
        assert len(rev_rows) == 1

    # Verify /analysis separates Observation vs Tentative Interpretation + anomalies + errors
    analysis = client.get(f"/api/v1/attempts/{attempt_id}/analysis", headers=AUTH_A).json()
    anomalies = analysis["speed_accuracy_anomalies"]
    assert anomalies["outlier_latency_count"] == 1
    assert len(anomalies["slow_questions"]) >= 1
    assert anomalies["slow_questions"][0]["is_outlier_capped"] is True
    assert anomalies["slow_questions"][0]["time_spent_ms"] == 300_000
    assert len(anomalies["fast_incorrect_questions"]) >= 1
    assert anomalies["summary_observation"] != anomalies["summary_interpretation"]

    err_cats = {e["error_category"]: e for e in analysis["error_patterns"]}
    assert "guess_low_confidence" in err_cats
    assert "calculation_error" in err_cats
    assert "not_attempted" in err_cats
    assert "answer_key_source_ambiguity" in err_cats
    for err in analysis["error_patterns"]:
        assert err["is_tentative"] is True
        assert len(err["observation"]) > 0
        assert len(err["possible_interpretation"]) > 0
        assert len(err["evidence_signals"]) >= 1

    # Verify 0-answered attempt edge case (all skipped -> accuracy None, avg_time_ms 0)
    all_skip_test = client.post(
        "/api/v1/tests",
        json={
            "title": "Zero Answered Edge",
            "question_ids": small_q_ids,
            "question_count": 3,
            "timer_mode": "learning_mode",
        },
        headers=AUTH_A,
    ).json()
    zero_att = client.post(f"/api/v1/tests/{all_skip_test['id']}/start", headers=AUTH_A).json()
    client.post(f"/api/v1/attempts/{zero_att['attempt_id']}/submit", headers=AUTH_A)
    zero_analysis = client.get(
        f"/api/v1/attempts/{zero_att['attempt_id']}/analysis", headers=AUTH_A
    ).json()
    assert zero_analysis["topic_classifications"][0]["status"] == "insufficient_data"
    assert zero_analysis["topic_classifications"][0]["accuracy_percent"] is None
    assert zero_analysis["topic_classifications"][0]["average_time_ms"] == 0


# ---------------------------------------------------------------------------
# 4. Rule-based Improvement Plan + Grounded AI Coaching (valid & fallback)
# ---------------------------------------------------------------------------


def test_improvement_plan_rules_linked_notes_and_grounded_ai_coaching_fallback(
    m7_env: tuple[TestClient, MutableClock, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, clock, mock_provider, session_factory = m7_env

    with session_factory() as db:
        doc = Document(
            user_id=uuid.UUID(USER_A),
            title="Algebra Source",
            original_filename="algebra.pdf",
            source_type="pdf",
            mime_type="application/pdf",
            file_size_bytes=512,
            sha256=uuid.uuid4().hex + "0" * 32,
            storage_key="users/u/doc/algebra.pdf",
            subject_code="quantitative_aptitude",
            status="knowledge_ready",
        )
        db.add(doc)
        db.flush()

        weak_topic, weak_q_ids = _create_topic_with_questions(
            db,
            subject_code="quantitative_aptitude",
            topic_name="Algebra",
            count=5,
            document_id=doc.id,
        )
        note = Note(
            document_id=doc.id,
            topic_id=weak_topic.id,
            subject_code="quantitative_aptitude",
            note_type="quick_revision",
            title="Algebra Quick Revision",
            content_json={"summary": "Core identities", "sections": []},
            status="ready",
        )
        db.add(note)
        db.commit()
        note_id = str(note.id)

    test_id = client.post(
        "/api/v1/tests",
        json={
            "title": "Algebra Diagnostic",
            "question_ids": weak_q_ids,
            "question_count": 5,
            "timer_mode": "speed_challenge",
            "per_question_seconds": 35,
        },
        headers=AUTH_A,
    ).json()["id"]
    start = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A).json()
    attempt_id = start["attempt_id"]

    # Let first 3 questions time out (timeout ratio >= 0.2), answer 4 & 5 wrong -> <50%
    for idx in range(5):
        if idx < 3:
            clock.advance(seconds=37)
            client.get(f"/api/v1/attempts/{attempt_id}/current", headers=AUTH_A)
        else:
            cur = client.get(f"/api/v1/attempts/{attempt_id}/current", headers=AUTH_A).json()
            clock.advance(seconds=10)
            client.post(
                f"/api/v1/attempts/{attempt_id}/responses",
                json={
                    "test_question_id": cur["current_question"]["test_question_id"],
                    "selected_option_key": "A",
                    "action": "answer",
                },
                headers=AUTH_A,
            )
    client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=AUTH_A)

    # GET before POST returns 404
    assert (
        client.get(f"/api/v1/attempts/{attempt_id}/improvement-plan", headers=AUTH_A).status_code
        == 404
    )

    # 1. Grounded LLM coaching succeeds ("generated")
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "summary_text": (
                    "Across 5 questions, 0 were correct and 3 timed out under the 35s limit."
                ),
                "topic_explanations": [
                    {
                        "topic_name": "Algebra",
                        "explanation": "Revising Algebra notes can help before timed sets.",
                    }
                ],
            }
        ),
        prompt_name="performance_coaching",
    )
    plan_ok = client.post(
        f"/api/v1/attempts/{attempt_id}/improvement-plan",
        json={"include_ai_coaching": True},
        headers=AUTH_A,
    )
    assert plan_ok.status_code == 200, plan_ok.text
    p1 = plan_ok.json()
    assert p1["ai_coaching"]["status"] == "generated"
    assert p1["ai_coaching"]["grounded_only"] is True
    action_types = {r["action_type"] for r in p1["recommendations"]}
    assert "concept_revision" in action_types
    assert "shorter_timed_sets_and_question_selection" in action_types
    alg_rec = next(r for r in p1["recommendations"] if r["topic_name"] == "Algebra")
    assert note_id in alg_rec["recommended_note_ids"]
    assert alg_rec["targeted_practice_preset"] is not None

    # GET /improvement-plan returns persisted plan with zero LLM calls
    calls_before = len(mock_provider.calls)
    saved_get = client.get(f"/api/v1/attempts/{attempt_id}/improvement-plan", headers=AUTH_A)
    assert saved_get.status_code == 200
    assert saved_get.json()["id"] == p1["id"]
    assert len(mock_provider.calls) == calls_before

    # 2. Hallucinated/ungrounded numbers (99.7% and 42) rejected -> "fallback"
    mock_provider.enqueue_raw(
        json.dumps(
            {
                "summary_text": "Your percentile is 99.7% after solving 42 bonus items.",
                "topic_explanations": [],
            }
        ),
        prompt_name="performance_coaching",
    )
    plan_fb = client.post(
        f"/api/v1/attempts/{attempt_id}/improvement-plan",
        json={"include_ai_coaching": True, "force_regenerate": True},
        headers=AUTH_A,
    )
    assert plan_fb.status_code == 200
    p2 = plan_fb.json()
    assert p2["plan_version"] == 2
    assert p2["ai_coaching"]["status"] == "fallback"
    assert p2["ai_coaching"]["grounded_only"] is True
    assert "99.7" not in p2["ai_coaching"]["summary_text"]


# ---------------------------------------------------------------------------
# 5. Multi-attempt deltas, targeted practice, revisions, dashboard, and 403s
# ---------------------------------------------------------------------------


def test_trends_deltas_targeted_practice_revisions_dashboard_and_403_isolation(
    m7_env: tuple[TestClient, MutableClock, MockLLMProvider, sessionmaker[Session]],
) -> None:
    client, clock, _, session_factory = m7_env

    with session_factory() as db:
        doc = Document(
            user_id=uuid.UUID(USER_A),
            title="Geometry Pack",
            original_filename="geom.pdf",
            source_type="pdf",
            mime_type="application/pdf",
            file_size_bytes=256,
            sha256=uuid.uuid4().hex + "0" * 32,
            storage_key="users/u/doc/geom.pdf",
            subject_code="quantitative_aptitude",
            status="knowledge_ready",
        )
        db.add(doc)
        db.flush()

        topic, q_ids = _create_topic_with_questions(
            db,
            subject_code="quantitative_aptitude",
            topic_name="Geometry",
            count=5,
            document_id=doc.id,
        )
        note = Note(
            document_id=doc.id,
            topic_id=topic.id,
            subject_code="quantitative_aptitude",
            note_type="detailed",
            title="Geometry Notes",
            content_json={"summary": "Triangles", "sections": []},
            status="ready",
        )
        db.add(note)
        db.commit()
        topic_id = str(topic.id)

    test_id = client.post(
        "/api/v1/tests",
        json={
            "title": "Geometry Quiz",
            "question_ids": q_ids,
            "question_count": 5,
            "timer_mode": "learning_mode",
        },
        headers=AUTH_A,
    ).json()["id"]

    # Attempt 1: 1/5 correct = 20.00%, 20s each
    a1 = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A).json()
    for idx, p in enumerate(a1["palette"]):
        if idx > 0:
            client.post(
                f"/api/v1/attempts/{a1['attempt_id']}/navigate",
                json={"target_index": idx},
                headers=AUTH_A,
            )
        clock.advance(seconds=20)
        client.post(
            f"/api/v1/attempts/{a1['attempt_id']}/responses",
            json={
                "test_question_id": p["test_question_id"],
                "selected_option_key": "B" if idx == 0 else "A",
                "action": "answer",
            },
            headers=AUTH_A,
        )
    client.post(f"/api/v1/attempts/{a1['attempt_id']}/submit", headers=AUTH_A)

    # Attempt 2: 4/5 correct = 80.00%, 10s each -> cumulative (1+4)/10 = 50.00%, prev 20.00%
    a2 = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A).json()
    for idx, p in enumerate(a2["palette"]):
        if idx > 0:
            client.post(
                f"/api/v1/attempts/{a2['attempt_id']}/navigate",
                json={"target_index": idx},
                headers=AUTH_A,
            )
        clock.advance(seconds=10)
        client.post(
            f"/api/v1/attempts/{a2['attempt_id']}/responses",
            json={
                "test_question_id": p["test_question_id"],
                "selected_option_key": "B" if idx < 4 else "A",
                "action": "answer",
            },
            headers=AUTH_A,
        )
    client.post(f"/api/v1/attempts/{a2['attempt_id']}/submit", headers=AUTH_A)

    # Topic trends & comparison_to_previous
    trends = client.get(
        f"/api/v1/performance/topics/{topic_id}/trends", headers=AUTH_A
    ).json()
    assert len(trends["points"]) == 2
    assert Decimal(trends["points"][0]["accuracy_percent"]) == Decimal("20.00")
    assert Decimal(trends["points"][1]["accuracy_percent"]) == Decimal("80.00")
    assert len(trends["recommended_notes"]) == 1

    a2_analysis = client.get(
        f"/api/v1/attempts/{a2['attempt_id']}/analysis", headers=AUTH_A
    ).json()
    delta = a2_analysis["comparison_to_previous"][0]
    assert Decimal(delta["previous_accuracy_percent"]) == Decimal("20.00")
    assert Decimal(delta["current_accuracy_percent"]) == Decimal("80.00")
    assert Decimal(delta["accuracy_delta_percent"]) == Decimal("60.00")

    overview = client.get("/api/v1/performance/overview", headers=AUTH_A).json()
    assert overview["total_attempts"] == 2
    assert len(overview["developing_topics"]) == 1  # cumulative 50.00% -> developing

    # Targeted practice creation (201) + insufficient pool (422)
    tp_resp = client.post(
        "/api/v1/performance/targeted-practice",
        json={"topic_ids": [topic_id], "question_count": 5, "timer_mode": "learning_mode"},
        headers=AUTH_A,
    )
    assert tp_resp.status_code == 201, tp_resp.text
    assert tp_resp.json()["test"]["total_questions"] == 5
    assert len(tp_resp.json()["linked_note_ids"]) == 1

    tp_fail = client.post(
        "/api/v1/performance/targeted-practice",
        json={"topic_ids": [topic_id], "question_count": 50},
        headers=AUTH_A,
    )
    assert tp_fail.status_code == 422

    # Revisions GET & PATCH
    revs = client.get("/api/v1/performance/revisions", headers=AUTH_A).json()
    assert revs["total"] >= 1
    rev_id = revs["items"][0]["id"]
    rev_patch = client.patch(
        f"/api/v1/performance/revisions/{rev_id}",
        json={"status": "completed"},
        headers=AUTH_A,
    )
    assert rev_patch.status_code == 200
    assert rev_patch.json()["status"] == "completed"

    # Start a 3rd in-progress attempt so dashboard `continue_attempt` is populated
    a3 = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A).json()
    dash = client.get("/api/v1/dashboard", headers=AUTH_A).json()
    assert dash["continue_attempt"]["attempt_id"] == a3["attempt_id"]
    assert dash["totals"]["documents_count"] == 1
    assert dash["totals"]["notes_count"] == 1
    assert dash["totals"]["questions_count"] == 5
    assert dash["totals"]["completed_attempts_count"] == 2
    assert len(dash["recent_documents"]) == 1
    assert len(dash["recent_attempts"]) == 2

    # Cross-user 403 & isolation
    assert (
        client.get(f"/api/v1/attempts/{a2['attempt_id']}/analysis", headers=AUTH_B).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/attempts/{a2['attempt_id']}/improvement-plan", json={}, headers=AUTH_B
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/attempts/{a2['attempt_id']}/improvement-plan", headers=AUTH_B
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/performance/revisions/{rev_id}",
            json={"status": "dismissed"},
            headers=AUTH_B,
        ).status_code
        == 403
    )
    assert client.get("/api/v1/performance/overview", headers=AUTH_B).json()["total_attempts"] == 0
    assert client.get("/api/v1/performance/topics", headers=AUTH_B).json()["total"] == 0
    assert client.get("/api/v1/performance/revisions", headers=AUTH_B).json()["total"] == 0
    dash_b = client.get("/api/v1/dashboard", headers=AUTH_B).json()
    assert dash_b["totals"]["documents_count"] == 0
    assert dash_b["totals"]["completed_attempts_count"] == 0
