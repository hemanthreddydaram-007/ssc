from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import ExamConfig


class ExamConfigRepository:
    """Data-access layer for versioned exam configuration records."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_all(self) -> list[ExamConfig]:
        """Return all exam configurations ordered deterministically by name."""
        stmt = select(ExamConfig).order_by(ExamConfig.name.asc(), ExamConfig.created_at.asc())
        return list(self._db.scalars(stmt).all())

    def get_by_exam_code(self, exam_code: str) -> ExamConfig | None:
        """Fetch an exam configuration by its unique `exam_code`."""
        stmt = select(ExamConfig).where(ExamConfig.exam_code == exam_code)
        return self._db.scalars(stmt).first()

    def get_by_id(self, exam_config_id: UUID) -> ExamConfig | None:
        """Fetch an exam configuration by primary key."""
        return self._db.get(ExamConfig, exam_config_id)

    def create(self, exam_config: ExamConfig) -> ExamConfig:
        """Persist a new ExamConfig record."""
        self._db.add(exam_config)
        self._db.commit()
        self._db.refresh(exam_config)
        return exam_config
