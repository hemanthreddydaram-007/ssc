from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.health as health_module
import app.main as main_module
from app.core.config import BACKEND_DIR, REPO_ROOT, Settings, get_settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.user import ExamConfig, User


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_returns_200_ok(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "connected"
    assert payload["app"] == "AI Exam Coach"
    assert payload["environment"] == "test"
    assert "timestamp" in payload


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_returns_503_when_db_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setattr(health_module, "check_db_health", lambda _db: False)
    response = client.get(path)
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"] == "unavailable"


def test_startup_seeds_default_user_and_ssc_chsl_config(
    client: TestClient,
    db_session: Session,
    test_settings: Settings,
) -> None:
    # client fixture runs FastAPI lifespan startup seeding
    _ = client.get("/health")

    default_user = db_session.get(User, test_settings.local_default_user_id)
    assert default_user is not None
    assert default_user.display_name == test_settings.local_default_user_name

    exam = (
        db_session.query(ExamConfig)
        .filter(ExamConfig.exam_code == "ssc_chsl_tier_1")
        .first()
    )
    assert exam is not None
    assert exam.name == "SSC CHSL Tier 1"
    assert exam.config_json["default_speed_challenge_seconds"] == 35
    assert set(exam.config_json["subjects"]) == {
        "quantitative_aptitude",
        "reasoning",
        "english",
        "general_awareness",
    }


def _build_auth_probe_app(
    db_session: Session,
    settings_override: Settings,
) -> FastAPI:
    probe = FastAPI()

    @probe.get("/whoami")
    def whoami(current_user: CurrentUser = Depends(get_current_user)) -> dict[str, str]:
        return {"id": str(current_user.id), "display_name": current_user.display_name}

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    probe.dependency_overrides[get_db] = _override_db
    probe.dependency_overrides[get_settings] = lambda: settings_override
    return probe


def test_get_current_user_dev_header_valid_and_invalid(
    db_session: Session,
    test_settings: Settings,
) -> None:
    probe = _build_auth_probe_app(db_session, test_settings)
    with TestClient(probe) as probe_client:
        # Default local user when header omitted
        default_resp = probe_client.get("/whoami")
        assert default_resp.status_code == 200
        assert default_resp.json()["id"] == str(test_settings.local_default_user_id)

        # Valid X-User-Id header switches active user in dev_header mode
        custom_id = UUID("00000000-0000-0000-0000-000000000099")
        custom_resp = probe_client.get("/whoami", headers={"X-User-Id": str(custom_id)})
        assert custom_resp.status_code == 200
        assert custom_resp.json()["id"] == str(custom_id)
        assert db_session.get(User, custom_id) is not None

        # Invalid UUID returns 400
        invalid_resp = probe_client.get("/whoami", headers={"X-User-Id": "not-a-uuid"})
        assert invalid_resp.status_code == 400


def test_get_current_user_blocks_header_override_in_production_and_single_user(
    db_session: Session,
    tmp_path: Path,
) -> None:
    custom_header = {"X-User-Id": "00000000-0000-0000-0000-000000000099"}

    prod_settings = Settings(
        app_env="production",
        auth_mode="dev_header",
        database_url=f"sqlite:///{(tmp_path / 'unused.db').as_posix()}",
        storage_root=tmp_path / "storage",
    )
    with TestClient(_build_auth_probe_app(db_session, prod_settings)) as prod_client:
        resp = prod_client.get("/whoami", headers=custom_header)
        assert resp.status_code == 403

    single_user_settings = Settings(
        app_env="development",
        auth_mode="single_user",
        database_url=f"sqlite:///{(tmp_path / 'unused.db').as_posix()}",
        storage_root=tmp_path / "storage",
    )
    with TestClient(_build_auth_probe_app(db_session, single_user_settings)) as single_client:
        resp = single_client.get("/whoami", headers=custom_header)
        assert resp.status_code == 403


def test_gitignore_excludes_env_and_private_storage() -> None:
    gitignore_path = REPO_ROOT / ".gitignore"
    assert gitignore_path.is_file()
    lines = {line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()}
    assert ".env" in lines
    assert ".env.*" in lines
    assert "!.env.example" in lines
    assert "storage/" in lines


def test_alembic_upgrade_downgrade_upgrade_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alembic_db_path = tmp_path / "alembic_cycle.db"
    db_url = f"sqlite:///{alembic_db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))

        command.upgrade(alembic_cfg, "head")
        engine = create_engine(db_url)
        try:
            tables_after_up = set(inspect(engine).get_table_names())
            assert {"users", "exam_configs", "documents", "questions", "attempts"}.issubset(
                tables_after_up
            )
        finally:
            engine.dispose()

        command.downgrade(alembic_cfg, "base")
        engine = create_engine(db_url)
        try:
            tables_after_down = set(inspect(engine).get_table_names())
            assert tables_after_down <= {"alembic_version"}
        finally:
            engine.dispose()

        command.upgrade(alembic_cfg, "head")
        engine = create_engine(db_url)
        try:
            tables_after_reup = set(inspect(engine).get_table_names())
            assert {"users", "exam_configs", "documents", "questions", "attempts"}.issubset(
                tables_after_reup
            )
            # Verify lifespan seeding works on freshly migrated DB
            session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
            monkeypatch.setattr(main_module, "SessionLocal", session_local)
            with TestClient(main_module.create_app()) as migrated_client:
                assert migrated_client.get("/health").status_code == 200
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()
