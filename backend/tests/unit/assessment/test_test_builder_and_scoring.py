from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.attempts import router as attempts_router
from app.api.v1.tests import router as tests_router
from app.core.config import Settings
from app.db.base import utcnow
from app.db.seed import seed_defaults
from app.db.session import get_db
from app.models.assessment import Question, QuestionOption, TestQuestion
from app.models.learning import Topic
from app.services.assessment.scoring_service import ScoringService
from app.services.question_generation.deduplicator import compute_stem_hash


def _build_client(db_session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(tests_router, prefix="/api/v1")
    app.include_router(attempts_router, prefix="/api/v1")

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _seed_verified_questions(db_session: Session, user_id: UUID) -> list[Question]:
    topic = Topic(subject_code="quantitative_aptitude", name="Percentages", slug="pct-m6")
    db_session.add(topic)
    db_session.flush()

    passage_gid = uuid4()
    items: list[tuple[str, str, str, UUID | None]] = [
        ("What is 10% of 100?", "easy", "A", None),
        ("What is 20% of 100?", "medium", "B", passage_gid),
        ("What is 30% of 100?", "medium", "C", passage_gid),
        ("What is 40% of 100?", "hard", "D", None),
    ]
    created: list[Question] = []
    base_ts = utcnow()
    for idx, (stem, diff, correct_key, pgid) in enumerate(items):
        q = Question(
            topic_id=topic.id,
            subject_code="quantitative_aptitude",
            question_text=stem,
            question_type="single_choice",
            difficulty=diff,
            origin="extracted",
            stem_hash=compute_stem_hash(stem),
            correct_answer_data={
                "correct_option_key": correct_key,
                "owner_user_id": str(user_id),
            },
            explanation=f"Explanation for {stem}",
            answer_key_provenance="deterministic_solver",
            validation_status="verified",
            passage_group_id=pgid,
            passage_text="Shared DI table passage." if pgid else None,
            created_at=base_ts + timedelta(seconds=idx),
        )
        db_session.add(q)
        db_session.flush()
        opts = [
            QuestionOption(
                question_id=q.id,
                option_key=k,
                option_text=f"{(i + 1) * 10}",
                display_order=i,
            )
            for i, k in enumerate(("A", "B", "C", "D"))
        ]
        for o in opts:
            db_session.add(o)
        created.append(q)
    db_session.commit()
    return created


def test_test_preview_create_snapshot_isolation_and_passage_contiguity(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    questions = _seed_verified_questions(db_session, test_settings.local_default_user_id)

    with _build_client(db_session) as client:
        preview_ok = client.post(
            "/api/v1/tests/preview",
            json={"question_count": 4, "subject_codes": ["quantitative_aptitude"]},
        )
        assert preview_ok.status_code == 200
        pdata = preview_ok.json()
        assert pdata["available_count"] == 4
        assert pdata["can_satisfy"] is True
        assert pdata["by_difficulty"] == {"easy": 1, "medium": 2, "hard": 1}

        preview_short = client.post(
            "/api/v1/tests/preview",
            json={"question_count": 10},
        )
        assert preview_short.status_code == 200
        assert preview_short.json()["can_satisfy"] is False
        assert preview_short.json()["shortfall_reason"] is not None

        too_many = client.post(
            "/api/v1/tests",
            json={"title": "Too Big", "question_count": 10},
        )
        assert too_many.status_code == 422

        created_resp = client.post(
            "/api/v1/tests",
            json={
                "title": "Snapshot Test",
                "question_count": 4,
                "shuffle_questions": True,
                "shuffle_options": True,
                "points_per_question": "2.00",
                "negative_marking_enabled": True,
                "negative_points": "0.50",
            },
        )
        assert created_resp.status_code == 201, created_resp.text
        test_data = created_resp.json()
        test_id = UUID(test_data["id"])
        assert test_data["total_questions"] == 4
        assert Decimal(test_data["max_score"]) == Decimal("8.00")
        assert "correct_option_key" not in str(test_data)

        # Verify passage_group_id questions stayed adjacent despite shuffle_questions=True
        tqs = list(
            db_session.execute(
                select(TestQuestion)
                .where(TestQuestion.test_id == test_id)
                .order_by(TestQuestion.display_order.asc())
            )
            .scalars()
            .all()
        )
        passage_indices = [i for i, tq in enumerate(tqs) if tq.passage_group_id is not None]
        assert len(passage_indices) == 2
        assert passage_indices[1] - passage_indices[0] == 1

        # Mutating source Question after test creation must NOT alter frozen TestQuestion snapshot
        original_q0_text = questions[0].question_text
        questions[0].question_text = "MUTATED AFTER CREATION"
        questions[0].correct_answer_data = {"correct_option_key": "D"}
        db_session.commit()

        reloaded_tqs = list(
            db_session.execute(select(TestQuestion).where(TestQuestion.test_id == test_id))
            .scalars()
            .all()
        )
        assert any(
            tq.question_snapshot_json["question_text"] == original_q0_text for tq in reloaded_tqs
        )
        assert all(
            tq.question_snapshot_json["question_text"] != "MUTATED AFTER CREATION"
            for tq in reloaded_tqs
        )


def test_scoring_service_decimal_precision_negative_marking_and_counts(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    _seed_verified_questions(db_session, test_settings.local_default_user_id)

    with _build_client(db_session) as client:
        test_resp = client.post(
            "/api/v1/tests",
            json={
                "title": "Scoring Check",
                "question_count": 4,
                "points_per_question": "2.00",
                "negative_marking_enabled": True,
                "negative_points": "0.33",
                "timer_mode": "exam_simulation",
                "total_duration_seconds": 300,
            },
        )
        assert test_resp.status_code == 201
        test_id = test_resp.json()["id"]

        start_resp = client.post(f"/api/v1/tests/{test_id}/start")
        assert start_resp.status_code == 201
        state = start_resp.json()
        attempt_id = state["attempt_id"]
        palette = state["palette"]

        # Q0 correct (+2.00)
        r0 = client.post(
            f"/api/v1/attempts/{attempt_id}/responses",
            json={"test_question_id": palette[0]["test_question_id"], "selected_option_key": "A"},
        )
        assert r0.status_code == 200
        # Q1 incorrect (-0.33)
        r1 = client.post(
            f"/api/v1/attempts/{attempt_id}/responses",
            json={"test_question_id": palette[1]["test_question_id"], "selected_option_key": "A"},
        )
        assert r1.status_code == 200
        # Q2 skipped (0.00)
        r2 = client.post(
            f"/api/v1/attempts/{attempt_id}/responses",
            json={"test_question_id": palette[2]["test_question_id"], "action": "skip"},
        )
        assert r2.status_code == 200
        # Q3 left unvisited -> becomes skipped on manual submit (0.00)

        sub1 = client.post(f"/api/v1/attempts/{attempt_id}/submit")
        assert sub1.status_code == 200
        summary = sub1.json()
        assert Decimal(summary["total_score"]) == Decimal("1.67")
        assert summary["correct_count"] == 1
        assert summary["incorrect_count"] == 1
        assert summary["skipped_count"] == 2
        assert summary["timed_out_count"] == 0

        # Idempotent double-submit returns identical summary
        sub2 = client.post(f"/api/v1/attempts/{attempt_id}/submit")
        assert sub2.status_code == 200
        assert sub2.json()["total_score"] == summary["total_score"]

        # Results endpoint returns full breakdowns & explanations
        res = client.get(f"/api/v1/attempts/{attempt_id}/results")
        assert res.status_code == 200
        rdata = res.json()
        assert Decimal(rdata["accuracy_attempted_percent"]) == Decimal("50.00")
        assert Decimal(rdata["accuracy_overall_percent"]) == Decimal("25.00")
        assert len(rdata["questions"]) == 4
        assert rdata["questions"][0]["correct_option_key"] == "A"
        assert "Explanation for" in rdata["questions"][0]["explanation"]
        _ = ScoringService


def test_scoring_normalizes_keys_protects_missing_key_and_detects_explanation_mismatch() -> None:
    import uuid  # noqa: PLC0415

    from app.models.assessment import Response, TestQuestion  # noqa: PLC0415
    from app.services.question_validation.math_solver import verify_question_math  # noqa: PLC0415

    scorer = ScoringService()

    # 1. Case/whitespace normalization matches cleanly
    tq_case = TestQuestion(
        id=uuid.uuid4(),
        test_id=uuid.uuid4(),
        display_order=0,
        question_snapshot_json={"answer_key": {"correct_option_key": " b "}},
        points=Decimal("2.00"),
        negative_points=Decimal("0.50"),
    )
    resp_case = Response(
        id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        test_question_id=tq_case.id,
        status="answered",
        selected_answer_json={"selected_option_key": "B"},
    )
    pts_case = scorer.grade_single_response(
        response=resp_case,
        test_question=tq_case,
        negative_marking_enabled=True,
    )
    assert resp_case.is_correct is True
    assert pts_case == Decimal("2.00")

    # 2. Missing answer key never marks response wrong or deducts negative points
    tq_nokey = TestQuestion(
        id=uuid.uuid4(),
        test_id=uuid.uuid4(),
        display_order=1,
        question_snapshot_json={"answer_key": {}},
        points=Decimal("2.00"),
        negative_points=Decimal("0.50"),
    )
    resp_nokey = Response(
        id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        test_question_id=tq_nokey.id,
        status="answered",
        selected_answer_json={"selected_option_key": "A"},
    )
    pts_nokey = scorer.grade_single_response(
        response=resp_nokey,
        test_question=tq_nokey,
        negative_marking_enabled=True,
    )
    assert resp_nokey.is_correct is None
    assert pts_nokey == Decimal("0.00")

    # 3. Explanation conclusion disagreeing with stored key is flagged as inconsistent
    check = verify_question_math(
        question_text=(
            "The equation of a line is 3x + 4y - 12 = 0. "
            "What is the slope of a line perpendicular to it?"
        ),
        options=[("A", "3/4"), ("B", "-3/4"), ("C", "4/3"), ("D", "-4/3")],
        correct_option_key="A",
        explanation="Solution gives m1 = -3/4, hence m2 = 4/3.",
    )
    assert check.checked is True
    assert check.is_consistent is False
    assert check.matched_option_keys == ["C"]
