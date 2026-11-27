from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db


@pytest.fixture
def isolated_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[Path, Path], None, None]:
    """Provide an isolated SQLite DB path and private storage path per test."""
    db_path = tmp_path / "test.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUTH_MODE", "dev_header")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_ROOT", str(storage_dir))
    get_settings.cache_clear()
    try:
        yield db_path, storage_dir
    finally:
        get_settings.cache_clear()


@pytest.fixture
def db_engine(isolated_env: tuple[Path, Path]) -> Generator[Engine, None, None]:
    """Create a schema-initialized SQLAlchemy engine on the isolated test DB."""
    db_path, _ = isolated_env
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session bound to the isolated test engine."""
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """Return a FastAPI TestClient wired to the isolated database and storage."""
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)

    app = main_module.create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def test_settings(isolated_env: tuple[Path, Path]) -> Settings:
    """Return fresh Settings loaded from the isolated test environment."""
    get_settings.cache_clear()
    return get_settings()
