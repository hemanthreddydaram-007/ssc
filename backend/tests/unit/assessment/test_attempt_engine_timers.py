from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.attempts import router as attempts_router
from app.api.v1.tests import router as tests_router
from app.core.config import Settings
from app.db.seed import seed_defaults
from app.db.session import get_db
from app.models.assessment import Question, QuestionOption
from app.models.user import User
from app.services.assessment.timer_service import get_clock
from app.services.question_generation.deduplicator import compute_stem_hash


class _FakeClock:
    def __init__(self, initial: datetime) -> None:
        self.now = initial

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: float = 0.0, milliseconds: float = 0.0) -> None:
        self.now = self.now + timedelta(seconds=seconds, milliseconds=milliseconds)


def _build_timed_client(db_session: Session, clock: _FakeClock) -> TestClient:
    app = FastAPI()
    app.include_router(tests_router, prefix="/api/v1")
    app.include_router(attempts_router, prefix="/api/v1")

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_clock] = lambda: clock
    return TestClient(app)


def _seed_two_questions(db_session: Session, user_id: UUID) -> None:
    for idx, (stem, correct_key) in enumerate(
        [("What is 5 + 5?", "B"), ("What is 6 + 6?", "C")]
    ):
        q = Question(
            subject_code="quantitative_aptitude",
            question_text=stem,
            question_type="single_choice",
            difficulty="easy",
            origin="extracted",
            stem_hash=compute_stem_hash(stem),
            correct_answer_data={"correct_option_key": correct_key, "owner_user_id": str(user_id)},
            explanation=f"Answer is {correct_key}.",
            answer_key_provenance="deterministic_solver",
            validation_status="verified",
        )
        db_session.add(q)
        db_session.flush()
        vals = ["8", "10", "12", "14"]
        for opt_idx, key in enumerate(("A", "B", "C", "D")):
            db_session.add(
                QuestionOption(
                    question_id=q.id,
                    option_key=key,
                    option_text=vals[opt_idx],
                    display_order=opt_idx,
                )
            )
        _ = idx
    db_session.commit()


def _collect_keys(obj: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(str(k))
            keys |= _collect_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _collect_keys(item)
    return keys


def _assert_no_answer_keys(payload: dict) -> None:
    keys = _collect_keys(payload)
    assert "correct_answer_data" not in keys
    assert "correct_option_key" not in keys
    assert "is_correct" not in keys
    assert "explanation" not in keys
    assert "answer_key" not in keys
    serialized = str(payload)
    assert "Answer is B." not in serialized
    assert "Answer is C." not in serialized


def test_speed_challenge_expiry_refresh_and_zero_answer_key_leak(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    _seed_two_questions(db_session, test_settings.local_default_user_id)
    clock = _FakeClock(datetime(2026, 11, 27, 12, 0, 0, tzinfo=UTC))

    with _build_timed_client(db_session, clock) as client:
        t_resp = client.post(
            "/api/v1/tests",
            json={
                "title": "Speed 35s",
                "question_count": 2,
                "timer_mode": "speed_challenge",
                "per_question_seconds": 35,
            },
        )
        assert t_resp.status_code == 201
        test_id = t_resp.json()["id"]

        start = client.post(f"/api/v1/tests/{test_id}/start")
        assert start.status_code == 201
        sdata = start.json()
        _assert_no_answer_keys(sdata)
        attempt_id = sdata["attempt_id"]
        q0_id = sdata["current_question"]["test_question_id"]
        assert sdata["current_question"]["question_remaining_seconds"] == 35

        # Refresh after 15 seconds: elapsed preserved, remaining is 20s
        clock.advance(seconds=15)
        cur = client.get(f"/api/v1/attempts/{attempt_id}/current")
        assert cur.status_code == 200
        cdata = cur.json()
        _assert_no_answer_keys(cdata)
        assert cdata["current_question"]["question_remaining_seconds"] == 20
        assert cdata["current_question"]["shown_at"] == sdata["current_question"]["shown_at"]

        # Navigation is blocked in Speed Challenge
        nav = client.post(f"/api/v1/attempts/{attempt_id}/navigate", json={"target_index": 1})
        assert nav.status_code == 400

        # Results blocked while in_progress
        early_res = client.get(f"/api/v1/attempts/{attempt_id}/results")
        assert early_res.status_code == 409
        assert early_res.json()["code"] == "ATTEMPT_IN_PROGRESS"

        # Advance past 35s + 1500ms grace -> late submission rejected as QUESTION_TIMED_OUT
        clock.advance(seconds=22)
        late = client.post(
            f"/api/v1/attempts/{attempt_id}/responses",
            json={"test_question_id": q0_id, "selected_option_key": "B"},
        )
        assert late.status_code == 409
        assert late.json()["code"] == "QUESTION_TIMED_OUT"

        # Cursor auto-advanced to Q1 with fresh 35s window
        cur2 = client.get(f"/api/v1/attempts/{attempt_id}/current").json()
        assert cur2["current_question_index"] == 1
        assert cur2["palette"][0]["status"] == "timed_out"
        q1_id = cur2["current_question"]["test_question_id"]

        # Answer Q1 within deadline (at +10s)
        clock.advance(seconds=10)
        ok_resp = client.post(
            f"/api/v1/attempts/{attempt_id}/responses",
            json={"test_question_id": q1_id, "selected_option_key": "C"},
        )
        assert ok_resp.status_code == 200
        _assert_no_answer_keys(ok_resp.json())

        sub = client.post(f"/api/v1/attempts/{attempt_id}/submit")
        assert sub.status_code == 200
        assert sub.json()["timed_out_count"] == 1
        assert sub.json()["correct_count"] == 1


def test_exam_simulation_total_expiry_navigation_and_learning_mode(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    _seed_two_questions(db_session, test_settings.local_default_user_id)
    other_id = UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_id, display_name="Other"))
    db_session.commit()

    clock = _FakeClock(datetime(2026, 11, 27, 12, 0, 0, tzinfo=UTC))

    with _build_timed_client(db_session, clock) as client:
        # 1. Exam Simulation
        sim_test = client.post(
            "/api/v1/tests",
            json={
                "title": "Sim 60s",
                "question_count": 2,
                "timer_mode": "exam_simulation",
                "total_duration_seconds": 60,
            },
        ).json()
        sim_start = client.post(f"/api/v1/tests/{sim_test['id']}/start").json()
        sim_attempt = sim_start["attempt_id"]
        assert sim_start["attempt_remaining_seconds"] == 60

        # Ownership check
        assert (
            client.get(
                f"/api/v1/attempts/{sim_attempt}/current",
                headers={"X-User-Id": str(other_id)},
            ).status_code
            == 403
        )

        # Navigate Q0 -> Q1 after 10s, then back Q1 -> Q0 after 5s
        clock.advance(seconds=10)
        nav1 = client.post(f"/api/v1/attempts/{sim_attempt}/navigate", json={"target_index": 1})
        assert nav1.status_code == 200
        assert nav1.json()["current_question_index"] == 1
        clock.advance(seconds=5)
        nav0 = client.post(f"/api/v1/attempts/{sim_attempt}/navigate", json={"target_index": 0})
        assert nav0.status_code == 200
        assert nav0.json()["current_question"]["time_spent_ms"] == 10000

        # Expire total duration (advance 50s -> total 65s > 60s + 1.5s grace)
        clock.advance(seconds=50)
        cur_after = client.get(f"/api/v1/attempts/{sim_attempt}/current").json()
        assert cur_after["status"] == "timed_out_submitted"
        assert cur_after["current_question"] is None

        # 2. Learning Mode with after_question feedback
        learn_test = client.post(
            "/api/v1/tests",
            json={
                "title": "Learning Drill",
                "question_count": 2,
                "timer_mode": "learning_mode",
                "show_explanation_after": "after_question",
                "hints_enabled": True,
            },
        ).json()
        l_start = client.post(f"/api/v1/tests/{learn_test['id']}/start").json()
        _assert_no_answer_keys(l_start)
        l_attempt = l_start["attempt_id"]
        q0_id = l_start["current_question"]["test_question_id"]
        assert l_start["current_question"]["hint"] is not None

        ans = client.post(
            f"/api/v1/attempts/{l_attempt}/responses",
            json={"test_question_id": q0_id, "selected_option_key": "B", "advance": False},
        )
        assert ans.status_code == 200
        adata = ans.json()
        assert adata["is_locked"] is True
        assert adata["locked_feedback"]["correct_option_key"] == "B"
        assert adata["locked_feedback"]["is_correct"] is True
        # Second question still has no answer key leaked in next_state
        _assert_no_answer_keys(adata["next_state"]["current_question"])

        # Cannot re-answer locked question in learning_mode
        reans = client.post(
            f"/api/v1/attempts/{l_attempt}/responses",
            json={"test_question_id": q0_id, "selected_option_key": "A"},
        )
        assert reans.status_code == 409
        assert reans.json()["code"] == "QUESTION_ALREADY_LOCKED"

        # Self-report and attempt listing work cleanly
        sr = client.patch(
            f"/api/v1/attempts/{l_attempt}/responses/{adata['response_id']}/self-report",
            json={"confidence_self_report": "high", "mistake_reason_self_report": "guessed"},
        )
        assert sr.status_code == 200
        assert sr.json()["confidence_self_report"] == "high"

        listed = client.get("/api/v1/attempts")
        assert listed.status_code == 200
        assert listed.json()["total"] == 2
