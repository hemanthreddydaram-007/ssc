from __future__ import annotations

from uuid import UUID

from app.models.user import ExamConfig
from app.repositories.exam_config_repo import ExamConfigRepository
from app.schemas.exam_config import (
    ExamConfigCreateRequest,
    ExamConfigListResponse,
    ExamConfigOut,
)


class ExamConfigNotFoundError(Exception):
    """Raised when a requested exam configuration code does not exist."""

    def __init__(self, exam_code: str) -> None:
        self.exam_code = exam_code
        super().__init__(f"Exam config '{exam_code}' not found")


class ExamConfigAlreadyExistsError(Exception):
    """Raised when creating an exam configuration with a duplicate `exam_code`."""

    def __init__(self, exam_code: str) -> None:
        self.exam_code = exam_code
        super().__init__(f"Exam config '{exam_code}' already exists")


class ExamConfigService:
    """Service for querying and registering exam configuration packs."""

    def __init__(self, repo: ExamConfigRepository) -> None:
        self._repo = repo

    def list_exam_configs(self) -> ExamConfigListResponse:
        """Return all configured exam packs with total count."""
        records = self._repo.list_all()
        items = [ExamConfigOut.model_validate(record) for record in records]
        return ExamConfigListResponse(items=items, total=len(items))

    def get_exam_config_by_code(self, exam_code: str) -> ExamConfigOut:
        """Return a single exam pack by `exam_code` or raise `ExamConfigNotFoundError`."""
        record = self._repo.get_by_exam_code(exam_code)
        if record is None:
            raise ExamConfigNotFoundError(exam_code)
        return ExamConfigOut.model_validate(record)

    def get_exam_config_by_id(self, exam_config_id: UUID) -> ExamConfigOut | None:
        """Return a single exam pack by UUID if it exists."""
        record = self._repo.get_by_id(exam_config_id)
        if record is None:
            return None
        return ExamConfigOut.model_validate(record)

    def create_exam_config(self, payload: ExamConfigCreateRequest) -> ExamConfigOut:
        """Register a new custom exam configuration pack."""
        existing = self._repo.get_by_exam_code(payload.exam_code)
        if existing is not None:
            raise ExamConfigAlreadyExistsError(payload.exam_code)

        config_json = dict(payload.config_json)
        config_json.setdefault("exam_code", payload.exam_code)
        config_json.setdefault("display_name", payload.name)

        record = ExamConfig(
            exam_code=payload.exam_code,
            name=payload.name,
            version=payload.version,
            config_json=config_json,
            source_url=payload.source_url,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
        )
        created = self._repo.create(record)
        return ExamConfigOut.model_validate(created)
