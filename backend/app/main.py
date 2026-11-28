from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.security import resolve_jwt_secret
from app.db.seed import seed_defaults
from app.db.session import SessionLocal
from app.repositories.job_repo import recover_stale_jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Ensure private storage exists, validate prod secrets, and seed baseline records."""
    settings = get_settings()
    resolve_jwt_secret(settings)
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        seed_defaults(db, settings)
        recovered = recover_stale_jobs(db, stale_after=None, ignore_heartbeats=True)
        if recovered:
            logger.warning("Recovered %d interrupted processing job(s) on startup", recovered)
    except Exception:
        logger.exception("Failed seeding baseline records or recovering stale jobs on startup")
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    """Construct the FastAPI modular monolith application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
