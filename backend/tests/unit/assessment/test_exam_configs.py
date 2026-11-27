from __future__ import annotations

from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.exam_configs import router as exam_configs_router
from app.core.config import Settings
from app.db.seed import seed_defaults
from app.db.session import get_db
from app.repositories.exam_config_repo import ExamConfigRepository
from app.services.assessment.exam_config_service import (
    ExamConfigNotFoundError,
    ExamConfigService,
)


def _build_exam_configs_test_client(db_session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(exam_configs_router, prefix="/api/v1")

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_list_and_get_seeded_exam_config_via_service(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)
    service = ExamConfigService(ExamConfigRepository(db_session))

    listing = service.list_exam_configs()
    assert listing.total == 1
    assert len(listing.items) == 1
    item = listing.items[0]
    assert item.exam_code == "ssc_chsl_tier_1"
    assert item.name == "SSC CHSL Tier 1"
    assert item.version == "1.0"
    assert item.config_json["default_speed_challenge_seconds"] == 35
    assert item.config_json["subjects"] == [
        "quantitative_aptitude",
        "reasoning",
        "english",
        "general_awareness",
    ]

    fetched = service.get_exam_config_by_code("ssc_chsl_tier_1")
    assert fetched.id == item.id
    assert service.get_exam_config_by_id(item.id) == fetched
    assert service.get_exam_config_by_id(item.id) is not None

    try:
        service.get_exam_config_by_code("nonexistent_exam")
        raise AssertionError("Expected ExamConfigNotFoundError")
    except ExamConfigNotFoundError as exc:
        assert exc.exam_code == "nonexistent_exam"


def test_exam_configs_routes_list_detail_create_and_conflict(
    db_session: Session,
    test_settings: Settings,
) -> None:
    seed_defaults(db_session, test_settings)

    with _build_exam_configs_test_client(db_session) as test_client:
        list_resp = test_client.get("/api/v1/exam-configs")
        assert list_resp.status_code == 200
        payload = list_resp.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        exam = payload["items"][0]
        assert set(exam.keys()) == {
            "id",
            "exam_code",
            "name",
            "version",
            "config_json",
            "source_url",
            "effective_from",
            "effective_to",
            "created_at",
        }
        assert exam["exam_code"] == "ssc_chsl_tier_1"

        detail_resp = test_client.get("/api/v1/exam-configs/ssc_chsl_tier_1")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == exam["id"]
        assert detail_resp.json()["config_json"]["supports_negative_marking"] is True

        missing_resp = test_client.get("/api/v1/exam-configs/unknown_exam")
        assert missing_resp.status_code == 404

        create_resp = test_client.post(
            "/api/v1/exam-configs",
            json={
                "exam_code": "ssc_cgl_tier_1",
                "name": "SSC CGL Tier 1",
                "version": "1.0",
                "config_json": {"subjects": ["quantitative_aptitude", "reasoning"]},
            },
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["exam_code"] == "ssc_cgl_tier_1"

        dup_resp = test_client.post(
            "/api/v1/exam-configs",
            json={"exam_code": "ssc_cgl_tier_1", "name": "Duplicate"},
        )
        assert dup_resp.status_code == 409
