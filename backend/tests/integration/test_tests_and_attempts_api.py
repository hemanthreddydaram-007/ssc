"""End-to-end integration tests for Milestone M6: Timed Test Engine & Test Player.

Covers all 5 verification gates from @coordinator #54:
  1. Test Builder & Snapshot Isolation: /tests/preview, /tests 422 shortfall, immutable
     snapshots immune to PATCH/DELETE /questions/{id}, contiguous passage_group_id under
     shuffle_questions=True, and option-shuffle grading integrity.
  2. Zero Answer-Key Leakage: recursive payload audit across /tests, /start, /current,
     /navigate, /responses in speed_challenge & exam_simulation + 409 on early /results.
  3. Speed Challenge: 35s default, within-1500ms grace succeeds, past-1500ms -> 409
     QUESTION_TIMED_OUT + auto-advance, browser refresh (/current) preserves server deadline.
  4. Exam Simulation & Learning Mode: /navigate + revisit time_spent_ms + mark_review +
     total duration auto-submit (409 ATTEMPT_EXPIRED); Learning Mode expires_at=None,
     after_question single-question locked_feedback + 409 QUESTION_ALREADY_LOCKED.
  5. Exact Decimal scoring (+2.00 / -0.50 / 0.00), idempotent double /submit,
     self-report tags, and cross-user 403 ownership enforcement.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.db.session import get_db
from app.models.assessment import Question, QuestionOption
from app.models.learning import Topic
from app.services.assessment.timer_service import get_clock

USER_A = "00000000-0000-0000-0000-000000000001"
USER_B = "00000000-0000-0000-0000-000000000002"
AUTH_A = {"X-User-Id": USER_A}
AUTH_B = {"X-User-Id": USER_B}

FORBIDDEN_ACTIVE_KEYS = {
    "correct_option_key",
    "correct_answer_data",
    "is_correct",
    "answer_key",
    "explanation",
}


class MutableClock:
    """Deterministic injectable UTC clock for testing server-authoritative timers."""

    def __init__(self, initial: datetime | None = None) -> None:
        self.now = initial or datetime(2026, 11, 27, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: float = 0, milliseconds: float = 0) -> datetime:
        self.now = self.now + timedelta(seconds=seconds, milliseconds=milliseconds)
        return self.now


def _assert_no_answer_key_leak(payload: Any, *, allow_locked_feedback: bool = False) -> None:
    """Recursively assert active-test JSON payloads contain zero answer keys/explanations."""
    if isinstance(payload, list):
        for item in payload:
            _assert_no_answer_key_leak(item, allow_locked_feedback=allow_locked_feedback)
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if allow_locked_feedback and key == "locked_feedback":
                continue
            assert key not in FORBIDDEN_ACTIVE_KEYS, (
                f"Active-test payload leaked forbidden key {key!r}: {payload}"
            )
            _assert_no_answer_key_leak(value, allow_locked_feedback=allow_locked_feedback)


@pytest.fixture
def m6_env(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, MutableClock, sessionmaker[Session]], None, None]:
    """Yield (TestClient, MutableClock, SessionLocal) with injectable get_clock."""
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)
    app = main_module.create_app()
    clock = MutableClock()

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_clock] = lambda: clock

    with TestClient(app) as tc:
        yield tc, clock, testing_session_local


def _seed_question_bank(
    session_factory: sessionmaker[Session],
    *,
    user_id: str = USER_A,
    count: int = 5,
    passage_pair: bool = False,
) -> list[str]:
    """Insert verified single-choice questions owned by `user_id` via standalone ownership."""
    created_ids: list[str] = []
    passage_gid = uuid.uuid4() if passage_pair else None

    with session_factory() as db:
        topic = Topic(
            subject_code="quantitative_aptitude",
            name="Percentages",
            slug=f"pct-{uuid.uuid4().hex[:6]}",
        )
        db.add(topic)
        db.flush()

        for idx in range(count):
            is_passage_q = passage_pair and idx in (1, 2)
            diff = ("easy", "medium", "hard")[idx % 3]
            q = Question(
                document_id=None,
                topic_id=topic.id,
                subject_code="quantitative_aptitude",
                question_text=f"Sample question #{idx + 1}: compute {10 + idx} + 5?",
                question_type="single_choice",
                difficulty=diff,
                origin="generated" if idx % 2 else "extracted",
                source_page_number=1,
                supporting_excerpt=f"Excerpt {idx + 1}",
                passage_group_id=passage_gid if is_passage_q else None,
                passage_text="Shared comprehension passage." if is_passage_q else None,
                stem_hash=uuid.uuid4().hex,
                correct_answer_data={
                    "correct_option_key": "B",
                    "owner_user_id": user_id,
                },
                explanation=f"Because {10 + idx} + 5 = {15 + idx} (Option B).",
                answer_key_provenance="source_answer_key",
                validation_status="verified",
            )
            db.add(q)
            db.flush()
            opts = [
                ("A", f"{14 + idx}"),
                ("B", f"{15 + idx}"),
                ("C", f"{16 + idx}"),
                ("D", f"{17 + idx}"),
            ]
            for o_idx, (ok, ot) in enumerate(opts):
                db.add(
                    QuestionOption(
                        question_id=q.id,
                        option_key=ok,
                        option_text=ot,
                        display_order=o_idx,
                    )
                )
            created_ids.append(str(q.id))

        db.commit()
    return created_ids


# ---------------------------------------------------------------------------
# 1 & 2. Test Builder, Snapshot Isolation, Passage Contiguity, Zero Leaks
# ---------------------------------------------------------------------------


def test_test_builder_preview_snapshots_passage_contiguity_and_zero_leaks(
    m6_env: tuple[TestClient, MutableClock, sessionmaker[Session]],
) -> None:
    client, _, session_factory = m6_env
    q_ids = _seed_question_bank(session_factory, count=5, passage_pair=True)

    # Preview shortfall check
    short_prev = client.post(
        "/api/v1/tests/preview",
        json={"question_count": 12, "subject_codes": ["quantitative_aptitude"]},
        headers=AUTH_A,
    )
    assert short_prev.status_code == 200
    sp_body = short_prev.json()
    assert sp_body["available_count"] == 5
    assert sp_body["can_satisfy"] is False
    assert sp_body["shortfall_reason"] is not None

    # Create with insufficient pool -> 422
    fail_create = client.post(
        "/api/v1/tests",
        json={"title": "Too Big", "question_count": 12},
        headers=AUTH_A,
    )
    assert fail_create.status_code == 422

    # Create valid test with shuffle_questions=True & shuffle_options=True
    create_resp = client.post(
        "/api/v1/tests",
        json={
            "title": "Quant Snapshot Pack",
            "question_ids": q_ids,
            "question_count": 5,
            "timer_mode": "exam_simulation",
            "total_duration_seconds": 300,
            "shuffle_questions": True,
            "shuffle_options": True,
            "points_per_question": "2.00",
            "negative_marking_enabled": True,
            "negative_points": "0.50",
        },
        headers=AUTH_A,
    )
    assert create_resp.status_code == 201, create_resp.text
    test_body = create_resp.json()
    test_id = test_body["id"]
    _assert_no_answer_key_leak(test_body)
    _assert_no_answer_key_leak(client.get("/api/v1/tests", headers=AUTH_A).json())
    _assert_no_answer_key_leak(client.get(f"/api/v1/tests/{test_id}", headers=AUTH_A).json())

    # Mutate & delete underlying Question Bank rows AFTER test creation
    edit_q = client.patch(
        f"/api/v1/questions/{q_ids[0]}",
        json={"question_text": "MUTATED QUESTION STEM!", "correct_option_key": "D"},
        headers=AUTH_A,
    )
    assert edit_q.status_code == 200
    del_q = client.delete(f"/api/v1/questions/{q_ids[4]}", headers=AUTH_A)
    assert del_q.status_code == 200

    # Start attempt -> verify zero answer key leaks, immutable snapshot, passage contiguity
    start_resp = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A)
    assert start_resp.status_code == 201, start_resp.text
    state = start_resp.json()
    attempt_id = state["attempt_id"]
    _assert_no_answer_key_leak(state)

    # Early /results must return 409 ATTEMPT_IN_PROGRESS
    early_res = client.get(f"/api/v1/attempts/{attempt_id}/results", headers=AUTH_A)
    assert early_res.status_code == 409
    assert early_res.json()["code"] == "ATTEMPT_IN_PROGRESS"

    # Visit all 5 questions in Exam Simulation, verify snapshots untouched & passage contiguous
    seen_passage_indices: list[int] = []
    for idx in range(5):
        if idx > 0:
            nav = client.post(
                f"/api/v1/attempts/{attempt_id}/navigate",
                json={"target_index": idx},
                headers=AUTH_A,
            )
            assert nav.status_code == 200
            state = nav.json()
            _assert_no_answer_key_leak(state)

        cur_q = state["current_question"]
        assert "MUTATED QUESTION STEM!" not in cur_q["question_text"]
        if cur_q["passage_group_id"] is not None:
            seen_passage_indices.append(idx)

        # Find option whose text corresponds to the correct answer (15 + original_idx)
        # Note: original stems are "compute {10 + i} + 5?", so correct text is "{15 + i}"
        stem = cur_q["question_text"]
        num_val = int(stem.split("compute ")[1].split(" +")[0])
        expected_ans = str(num_val + 5)
        chosen_key = next(o["key"] for o in cur_q["options"] if o["text"] == expected_ans)

        save_resp = client.post(
            f"/api/v1/attempts/{attempt_id}/responses",
            json={
                "test_question_id": cur_q["test_question_id"],
                "selected_option_key": chosen_key,
                "action": "answer",
                "advance": False,
            },
            headers=AUTH_A,
        )
        assert save_resp.status_code == 200
        _assert_no_answer_key_leak(save_resp.json())

    # Passage group questions must appear adjacently (difference == 1) even under shuffle
    assert len(seen_passage_indices) == 2
    assert abs(seen_passage_indices[1] - seen_passage_indices[0]) == 1

    # Submit and verify shuffle_options remapped answer keys graded all 5/5 correctly
    sub = client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=AUTH_A)
    assert sub.status_code == 200
    assert Decimal(sub.json()["total_score"]) == Decimal("10.00")
    assert sub.json()["correct_count"] == 5


# ---------------------------------------------------------------------------
# 3. Speed Challenge: 35s default, 1500ms grace, 409 timeout, browser refresh
# ---------------------------------------------------------------------------


def test_speed_challenge_default_35s_grace_timeout_and_refresh_recovery(
    m6_env: tuple[TestClient, MutableClock, sessionmaker[Session]],
) -> None:
    client, clock, session_factory = m6_env
    q_ids = _seed_question_bank(session_factory, count=3)

    # Default per_question_seconds == 35
    create_resp = client.post(
        "/api/v1/tests",
        json={
            "title": "Speed 35s Test",
            "question_ids": q_ids,
            "question_count": 3,
            "timer_mode": "speed_challenge",
        },
        headers=AUTH_A,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["settings_json"]["per_question_seconds"] == 35
    test_id = create_resp.json()["id"]

    start_state = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A).json()
    attempt_id = start_state["attempt_id"]
    _assert_no_answer_key_leak(start_state)
    assert start_state["current_question"]["question_remaining_seconds"] == 35

    # Navigate is forbidden (400) in Speed Challenge
    nav_err = client.post(
        f"/api/v1/attempts/{attempt_id}/navigate",
        json={"target_index": 1},
        headers=AUTH_A,
    )
    assert nav_err.status_code == 400

    # Simulated browser refresh at t+20s preserves deadline (15s left, does not reset)
    clock.advance(seconds=20)
    refreshed = client.get(f"/api/v1/attempts/{attempt_id}/current", headers=AUTH_A).json()
    _assert_no_answer_key_leak(refreshed)
    assert refreshed["current_question_index"] == 0
    assert refreshed["current_question"]["question_remaining_seconds"] == 15

    # Submit Q0 at t+36.0s (within 35s + 1500ms grace) -> succeeds & advances to Q1
    clock.advance(seconds=16)  # total 36.0s elapsed on Q0
    q0_id = refreshed["current_question"]["test_question_id"]
    save_q0 = client.post(
        f"/api/v1/attempts/{attempt_id}/responses",
        json={"test_question_id": q0_id, "selected_option_key": "B", "action": "answer"},
        headers=AUTH_A,
    )
    assert save_q0.status_code == 200, save_q0.text
    _assert_no_answer_key_leak(save_q0.json())
    q1_state = save_q0.json()["next_state"]
    assert q1_state["current_question_index"] == 1
    q1_id = q1_state["current_question"]["test_question_id"]

    # Advance past 35s + 1500ms grace on Q1 -> 409 QUESTION_TIMED_OUT & auto-advances to Q2
    clock.advance(seconds=37)
    late_q1 = client.post(
        f"/api/v1/attempts/{attempt_id}/responses",
        json={"test_question_id": q1_id, "selected_option_key": "B", "action": "answer"},
        headers=AUTH_A,
    )
    assert late_q1.status_code == 409
    assert late_q1.json()["code"] == "QUESTION_TIMED_OUT"

    # Refresh confirms cursor moved to Q2 and Q1 is marked timed_out
    q2_state = client.get(f"/api/v1/attempts/{attempt_id}/current", headers=AUTH_A).json()
    assert q2_state["current_question_index"] == 2
    assert q2_state["palette"][1]["status"] == "timed_out"

    # Let final Q2 expire past grace, then /current auto-submits attempt as timed_out_submitted
    clock.advance(seconds=37)
    final_state = client.get(f"/api/v1/attempts/{attempt_id}/current", headers=AUTH_A).json()
    assert final_state["status"] == "timed_out_submitted"

    results = client.get(f"/api/v1/attempts/{attempt_id}/results", headers=AUTH_A).json()
    assert results["correct_count"] == 1
    assert results["timed_out_count"] == 2


# ---------------------------------------------------------------------------
# 4. Exam Simulation expiry & Learning Mode single-question locked feedback
# ---------------------------------------------------------------------------


def test_exam_simulation_revisit_expiry_and_learning_mode_locked_feedback(
    m6_env: tuple[TestClient, MutableClock, sessionmaker[Session]],
) -> None:
    client, clock, session_factory = m6_env
    q_ids = _seed_question_bank(session_factory, count=3)

    # --- Exam Simulation ---
    sim_test = client.post(
        "/api/v1/tests",
        json={
            "title": "Exam Sim 120s",
            "question_ids": q_ids,
            "question_count": 3,
            "timer_mode": "exam_simulation",
            "total_duration_seconds": 120,
        },
        headers=AUTH_A,
    ).json()
    sim_start = client.post(f"/api/v1/tests/{sim_test['id']}/start", headers=AUTH_A).json()
    sim_id = sim_start["attempt_id"]
    _assert_no_answer_key_leak(sim_start)
    assert sim_start["attempt_remaining_seconds"] == 120

    # Spend 10s on Q0, mark for review, navigate to Q1, spend 15s, return to Q0, spend 5s
    clock.advance(seconds=10)
    q0_id = sim_start["current_question"]["test_question_id"]
    mark_res = client.post(
        f"/api/v1/attempts/{sim_id}/responses",
        json={"test_question_id": q0_id, "action": "mark_review"},
        headers=AUTH_A,
    )
    assert mark_res.status_code == 200
    assert mark_res.json()["is_marked_for_review"] is True

    nav1 = client.post(
        f"/api/v1/attempts/{sim_id}/navigate", json={"target_index": 1}, headers=AUTH_A
    ).json()
    _assert_no_answer_key_leak(nav1)
    clock.advance(seconds=15)

    nav_back = client.post(
        f"/api/v1/attempts/{sim_id}/navigate", json={"target_index": 0}, headers=AUTH_A
    ).json()
    _assert_no_answer_key_leak(nav_back)
    clock.advance(seconds=5)
    ans_q0 = client.post(
        f"/api/v1/attempts/{sim_id}/responses",
        json={
            "test_question_id": q0_id,
            "selected_option_key": "B",
            "action": "answer",
            "advance": False,
        },
        headers=AUTH_A,
    ).json()
    assert ans_q0["time_spent_ms"] == 15000  # 10s first visit + 5s second visit

    # Advance past 120s + 1500ms -> 409 ATTEMPT_EXPIRED and auto-submitted
    clock.advance(seconds=95)
    late_sim = client.post(
        f"/api/v1/attempts/{sim_id}/responses",
        json={"test_question_id": q0_id, "selected_option_key": "A", "action": "answer"},
        headers=AUTH_A,
    )
    assert late_sim.status_code == 409
    assert late_sim.json()["code"] == "ATTEMPT_EXPIRED"

    # --- Learning Mode (after_question) ---
    learn_test = client.post(
        "/api/v1/tests",
        json={
            "title": "Learning Mode Test",
            "question_ids": q_ids,
            "question_count": 3,
            "timer_mode": "learning_mode",
            "show_explanation_after": "after_question",
        },
        headers=AUTH_A,
    ).json()
    learn_start = client.post(f"/api/v1/tests/{learn_test['id']}/start", headers=AUTH_A).json()
    learn_id = learn_start["attempt_id"]
    assert learn_start["attempt_expires_at"] is None
    assert learn_start["locked_feedback"] is None
    _assert_no_answer_key_leak(learn_start)

    lq0_id = learn_start["current_question"]["test_question_id"]
    save_learn = client.post(
        f"/api/v1/attempts/{learn_id}/responses",
        json={
            "test_question_id": lq0_id,
            "selected_option_key": "B",
            "action": "answer",
            "advance": True,
        },
        headers=AUTH_A,
    )
    assert save_learn.status_code == 200
    sl_body = save_learn.json()
    assert sl_body["is_locked"] is True
    assert sl_body["locked_feedback"] is not None
    assert sl_body["locked_feedback"]["correct_option_key"] == "B"
    assert sl_body["locked_feedback"]["is_correct"] is True
    assert "Option B" in sl_body["locked_feedback"]["explanation"]
    # Remaining/next question in next_state MUST remain sealed!
    _assert_no_answer_key_leak(sl_body["next_state"], allow_locked_feedback=False)
    assert sl_body["next_state"]["current_question_index"] == 1

    # Re-answering locked question returns 409 QUESTION_ALREADY_LOCKED
    double_ans = client.post(
        f"/api/v1/attempts/{learn_id}/responses",
        json={"test_question_id": lq0_id, "selected_option_key": "A", "action": "answer"},
        headers=AUTH_A,
    )
    assert double_ans.status_code == 409
    assert double_ans.json()["code"] == "QUESTION_ALREADY_LOCKED"


# ---------------------------------------------------------------------------
# 5. Decimal scoring, negative marking, idempotent submit, self-report & 403
# ---------------------------------------------------------------------------


def test_decimal_scoring_idempotent_submit_self_report_and_403_isolation(
    m6_env: tuple[TestClient, MutableClock, sessionmaker[Session]],
) -> None:
    client, clock, session_factory = m6_env
    q_ids = _seed_question_bank(session_factory, count=4)

    test_row = client.post(
        "/api/v1/tests",
        json={
            "title": "Scoring Audit Pack",
            "question_ids": q_ids,
            "question_count": 4,
            "timer_mode": "exam_simulation",
            "total_duration_seconds": 600,
            "points_per_question": "2.00",
            "negative_marking_enabled": True,
            "negative_points": "0.50",
        },
        headers=AUTH_A,
    ).json()
    test_id = test_row["id"]
    start = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A).json()
    attempt_id = start["attempt_id"]

    # Q0 -> Correct (+2.00), Q1 -> Incorrect (-0.50), Q2 -> Skipped (0.00), Q3 -> Unvisited (0.00)
    q0_id = start["palette"][0]["test_question_id"]
    q1_id = start["palette"][1]["test_question_id"]
    q2_id = start["palette"][2]["test_question_id"]

    clock.advance(seconds=5)
    r0 = client.post(
        f"/api/v1/attempts/{attempt_id}/responses",
        json={"test_question_id": q0_id, "selected_option_key": "B", "action": "answer"},
        headers=AUTH_A,
    ).json()
    clock.advance(seconds=7)
    r1 = client.post(
        f"/api/v1/attempts/{attempt_id}/responses",
        json={"test_question_id": q1_id, "selected_option_key": "A", "action": "answer"},
        headers=AUTH_A,
    ).json()
    clock.advance(seconds=3)
    client.post(
        f"/api/v1/attempts/{attempt_id}/responses",
        json={"test_question_id": q2_id, "action": "skip"},
        headers=AUTH_A,
    )

    # Idempotent double submit -> +2.00 - 0.50 = 1.50
    sub1 = client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=AUTH_A).json()
    sub2 = client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=AUTH_A).json()
    assert sub1["status"] == "submitted"
    assert Decimal(sub1["total_score"]) == Decimal("1.50")
    assert Decimal(sub1["max_score"]) == Decimal("8.00")
    assert sub1["correct_count"] == 1
    assert sub1["incorrect_count"] == 1
    assert sub1["skipped_count"] == 2
    assert sub1["total_time_ms"] == 15000
    assert sub2 == sub1

    # Self-report mistake reason & confidence tags persisted & returned in /results
    sr = client.patch(
        f"/api/v1/attempts/{attempt_id}/responses/{r1['response_id']}/self-report",
        json={
            "confidence_self_report": "low",
            "mistake_reason_self_report": "knew_method_made_mistake",
        },
        headers=AUTH_A,
    )
    assert sr.status_code == 200
    assert sr.json()["mistake_reason_self_report"] == "knew_method_made_mistake"

    results = client.get(f"/api/v1/attempts/{attempt_id}/results", headers=AUTH_A).json()
    assert Decimal(results["accuracy_attempted_percent"]) == Decimal("50.00")
    assert Decimal(results["accuracy_overall_percent"]) == Decimal("25.00")
    assert len(results["topic_breakdown"]) >= 1
    assert len(results["difficulty_breakdown"]) >= 1
    q1_rev = next(q for q in results["questions"] if q["response_id"] == r1["response_id"])
    assert q1_rev["mistake_reason_self_report"] == "knew_method_made_mistake"
    assert q1_rev["confidence_self_report"] == "low"
    assert q1_rev["correct_option_key"] == "B"

    # Cross-user 403 ownership enforcement across all M6 endpoints
    assert client.get("/api/v1/tests", headers=AUTH_B).json()["total"] == 0
    assert client.get("/api/v1/attempts", headers=AUTH_B).json()["total"] == 0
    assert client.get(f"/api/v1/tests/{test_id}", headers=AUTH_B).status_code == 403
    assert client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_B).status_code == 403
    assert client.get(f"/api/v1/attempts/{attempt_id}/current", headers=AUTH_B).status_code == 403
    assert (
        client.post(
            f"/api/v1/attempts/{attempt_id}/navigate",
            json={"target_index": 0},
            headers=AUTH_B,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/attempts/{attempt_id}/responses",
            json={"test_question_id": q0_id, "action": "skip"},
            headers=AUTH_B,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/attempts/{attempt_id}/responses/{r0['response_id']}/self-report",
            json={"confidence_self_report": "high"},
            headers=AUTH_B,
        ).status_code
        == 403
    )
    assert client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=AUTH_B).status_code == 403
    assert client.get(f"/api/v1/attempts/{attempt_id}/results", headers=AUTH_B).status_code == 403
