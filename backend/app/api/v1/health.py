from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import check_db_health, get_db

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    auth_mode: str
    database: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
def health_check(
    response: Response,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> HealthResponse:
    """Report application and database readiness."""
    db_ok = check_db_health(db)
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        auth_mode=settings.effective_auth_mode,
        database="connected" if db_ok else "unavailable",
        timestamp=datetime.now(UTC),
    )
