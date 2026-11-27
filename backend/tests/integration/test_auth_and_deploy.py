"""Integration tests for Production JWT Auth, Rate Limiting, DB Normalization & Deploy Configs.

Covers all requirements from @coordinator #68:
  1. POST /api/v1/auth/register (201, scrypt hash stored, 409 duplicate email, 422 short pw).
  2. POST /api/v1/auth/login (200 Bearer JWT, 401 wrong password).
  3. AUTH_MODE=jwt & APP_ENV=production: missing token -> 401, X-User-Id spoof -> 403,
     valid Bearer JWT -> 200 (/auth/me), and cross-user 403 isolation on /documents.
  4. Startup resolve_jwt_secret raises RuntimeError if APP_ENV=production and JWT_SECRET_KEY
     is empty or < 32 characters (both directly and via TestClient lifespan).
  5. Sliding-window RateLimitMiddleware returns 429 RATE_LIMIT_EXCEEDED with Retry-After on
     auth & AI endpoint bursts (with rate_limiter.reset() cleanup).
  6. Settings._normalize_database_url converts postgres:// and postgresql:// to postgresql+psycopg://.
  7. Alembic upgrade head -> downgrade base -> upgrade head including
     dbbe0ed386ce_add_user_password_hash.
  8. Validation of render.yaml, backend/Dockerfile, and backend/railway.toml production keys.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.core.config import BACKEND_DIR, REPO_ROOT, Settings, get_settings
from app.core.rate_limit import rate_limiter
from app.core.security import resolve_jwt_secret
from app.db.session import get_db
from app.models.user import User

STRONG_PROD_SECRET = "prod-jwt-secret-key-at-least-32-chars-long-0123456789"


@pytest.fixture
def jwt_prod_env(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    """Yield (TestClient, SessionLocal) running in APP_ENV=production + AUTH_MODE=jwt."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET_KEY", STRONG_PROD_SECRET)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    rate_limiter.reset()

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
    try:
        with TestClient(app) as tc:
            yield tc, testing_session_local
    finally:
        rate_limiter.reset()
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 1, 2, 3. Register, Login, Production JWT Enforcement & Cross-User Isolation
# ---------------------------------------------------------------------------


def test_register_login_jwt_enforcement_and_cross_user_isolation(
    jwt_prod_env: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = jwt_prod_env

    # Short password rejected (422)
    short_pw = client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "123", "display_name": "Short"},
    )
    assert short_pw.status_code == 422

    # Valid registration -> 201 + JWT + scrypt password_hash in DB
    reg_a = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Aspirant.A@Example.com",
            "password": "StrongPassword!123",
            "display_name": "Aspirant A",
        },
    )
    assert reg_a.status_code == 201, reg_a.text
    body_a = reg_a.json()
    token_a = body_a["access_token"]
    assert body_a["token_type"] == "bearer"
    assert body_a["user"]["email"] == "aspirant.a@example.com"
    assert body_a["user"]["auth_mode"] == "jwt"

    with session_factory() as db:
        user_a = db.execute(select(User).where(User.email == "aspirant.a@example.com")).scalar_one()
        assert user_a.password_hash is not None
        assert user_a.password_hash.startswith("scrypt$")
        assert "StrongPassword!123" not in user_a.password_hash

    # Duplicate email -> 409
    dup = client.post(
        "/api/v1/auth/register",
        json={
            "email": "aspirant.a@example.com",
            "password": "AnotherPassword!123",
            "display_name": "Dup",
        },
    )
    assert dup.status_code == 409

    # Wrong password -> 401
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "aspirant.a@example.com", "password": "WrongPassword!999"},
    )
    assert bad_login.status_code == 401

    # Valid login -> 200 Bearer JWT
    good_login = client.post(
        "/api/v1/auth/login",
        json={"email": "aspirant.a@example.com", "password": "StrongPassword!123"},
    )
    assert good_login.status_code == 200
    token_a_login = good_login.json()["access_token"]

    # Production JWT enforcement: missing token -> 401, X-User-Id spoof -> 403
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/documents").status_code == 401
    assert (
        client.get(
            "/api/v1/documents",
            headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"},
        ).status_code
        == 403
    )

    # Valid Bearer JWT -> 200 on /auth/me & /documents
    headers_a = {"Authorization": f"Bearer {token_a_login}"}
    me_a = client.get("/api/v1/auth/me", headers=headers_a)
    assert me_a.status_code == 200
    assert me_a.json()["id"] == body_a["user"]["id"]

    # Register second JWT user & verify cross-user 403 isolation on /documents
    reg_b = client.post(
        "/api/v1/auth/register",
        json={
            "email": "aspirant.b@example.com",
            "password": "StrongPassword!456",
            "display_name": "Aspirant B",
        },
    )
    assert reg_b.status_code == 201
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

    up = client.post(
        "/api/v1/documents/text",
        json={"title": "User A Private Notes", "content": "Article 21 protects life."},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]

    assert client.get("/api/v1/documents", headers=headers_b).json()["total"] == 0
    assert client.get(f"/api/v1/documents/{doc_id}", headers=headers_b).status_code == 403


# ---------------------------------------------------------------------------
# 4. Production JWT secret startup guard
# ---------------------------------------------------------------------------


def test_resolve_jwt_secret_rejects_empty_or_short_secret_in_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for bad_secret in (None, "", "too-short-secret"):
        prod_bad = Settings(
            app_env="production",
            auth_mode="jwt",
            jwt_secret_key=bad_secret,  # type: ignore[arg-type]
            database_url=f"sqlite:///{(tmp_path / 'unused.db').as_posix()}",
            storage_root=tmp_path / "storage",
        )
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            resolve_jwt_secret(prod_bad)

    # Startup lifespan also enforces resolve_jwt_secret on boot
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET_KEY", "short")
    get_settings.cache_clear()
    try:
        app = main_module.create_app()
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            with TestClient(app):
                pass
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 5. Sliding-window rate limiter on auth and AI endpoints
# ---------------------------------------------------------------------------


def test_rate_limiter_enforces_auth_and_ai_bursts_with_retry_after(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "2")
    monkeypatch.setenv("RATE_LIMIT_AI_PER_MINUTE", "2")
    get_settings.cache_clear()
    rate_limiter.reset()

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
    try:
        with TestClient(app) as tc:
            # Auth burst: 2 allowed, 3rd -> 429 RATE_LIMIT_EXCEEDED + Retry-After
            for _ in range(2):
                r = tc.post(
                    "/api/v1/auth/login",
                    json={"email": "nobody@example.com", "password": "wrong"},
                )
                assert r.status_code == 401
            r_limited = tc.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "wrong"},
            )
            assert r_limited.status_code == 429
            assert r_limited.json()["code"] == "RATE_LIMIT_EXCEEDED"
            assert int(r_limited.headers["Retry-After"]) >= 1

            # AI route burst: 2 allowed (404 on missing doc), 3rd -> 429 RATE_LIMIT_EXCEEDED
            fake_doc_id = "00000000-0000-0000-0000-000000000099"
            for _ in range(2):
                r_ai = tc.post(f"/api/v1/documents/{fake_doc_id}/extract-knowledge", json={})
                assert r_ai.status_code == 404
            r_ai_limited = tc.post(f"/api/v1/documents/{fake_doc_id}/extract-knowledge", json={})
            assert r_ai_limited.status_code == 429
            assert r_ai_limited.json()["code"] == "RATE_LIMIT_EXCEEDED"
            assert int(r_ai_limited.headers["Retry-After"]) >= 1
    finally:
        rate_limiter.reset()
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 6. Database URL normalization
# ---------------------------------------------------------------------------


def test_settings_normalizes_postgres_database_urls(tmp_path: Path) -> None:
    s1 = Settings(
        database_url="postgres://user:pass@host:5432/examdb",
        storage_root=tmp_path / "s1",
    )
    s2 = Settings(
        database_url="postgresql://user:pass@host:5432/examdb",
        storage_root=tmp_path / "s2",
    )
    s3 = Settings(
        database_url="postgresql+psycopg://user:pass@host:5432/examdb",
        storage_root=tmp_path / "s3",
    )
    assert s1.database_url == "postgresql+psycopg://user:pass@host:5432/examdb"
    assert s2.database_url == "postgresql+psycopg://user:pass@host:5432/examdb"
    assert s3.database_url == "postgresql+psycopg://user:pass@host:5432/examdb"


# ---------------------------------------------------------------------------
# 7. Alembic migration round-trip with dbbe0ed386ce_add_user_password_hash
# ---------------------------------------------------------------------------


def test_alembic_roundtrip_includes_user_password_hash_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "alembic_auth.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()

    try:
        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        command.upgrade(alembic_cfg, "head")
        eng = create_engine(db_url)
        try:
            user_cols = {col["name"] for col in inspect(eng).get_columns("users")}
            assert "password_hash" in user_cols
        finally:
            eng.dispose()

        command.downgrade(alembic_cfg, "base")
        eng = create_engine(db_url)
        try:
            assert "users" not in set(inspect(eng).get_table_names())
        finally:
            eng.dispose()

        command.upgrade(alembic_cfg, "head")
        eng = create_engine(db_url)
        try:
            assert "password_hash" in {col["name"] for col in inspect(eng).get_columns("users")}
        finally:
            eng.dispose()
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 8. Production deployment manifests check
# ---------------------------------------------------------------------------


def test_deployment_manifests_contain_required_production_keys() -> None:
    render_yaml = REPO_ROOT / "render.yaml"
    dockerfile = BACKEND_DIR / "Dockerfile"
    railway_toml = BACKEND_DIR / "railway.toml"
    deploy_doc = REPO_ROOT / "docs" / "DEPLOYMENT.md"

    for path in (render_yaml, dockerfile, railway_toml, deploy_doc):
        assert path.is_file(), f"Missing deployment artifact: {path}"

    render_text = render_yaml.read_text(encoding="utf-8")
    for key in ("AUTH_MODE", "JWT_SECRET_KEY", "GEMINI_API_KEY", "STORAGE_ROOT", "/health"):
        assert key in render_text, f"Missing {key!r} in render.yaml"

    docker_text = dockerfile.read_text(encoding="utf-8")
    for token in ("alembic upgrade head", "AUTH_MODE=jwt", "APP_ENV=production", "uvicorn"):
        assert token in docker_text, f"Missing {token!r} in backend/Dockerfile"

    railway_text = railway_toml.read_text(encoding="utf-8")
    assert 'healthcheckPath = "/health"' in railway_text
