from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.performance_repo import PerformanceRepository
from app.schemas.performance import TargetedPracticeRequest, TargetedPracticeResponse
from app.schemas.test import DifficultyMix, TestCreateRequest
from app.services.assessment.test_builder import (
    TestBuilderService,
    TestBuildValidationError,
)


class TargetedPracticeValidationError(Exception):
    """Raised when targeted practice cannot be built from available questions."""


class TargetedPracticeService:
    """Creates targeted weak-topic practice tests and links supporting notes."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = PerformanceRepository(db)
        self._test_builder = TestBuilderService(db)

    def create_targeted_practice(
        self,
        *,
        user_id: UUID,
        payload: TargetedPracticeRequest,
    ) -> TargetedPracticeResponse:
        topics_map = self._repo.get_topic_names_map(set(payload.topic_ids))
        topic_names = [topics_map[tid].name for tid in payload.topic_ids if tid in topics_map]
        if topic_names:
            title_topics = ", ".join(topic_names[:2])
            if len(topic_names) > 2:
                title_topics += f" (+{len(topic_names) - 2})"
            title = f"Targeted Practice: {title_topics}"
        else:
            title = "Targeted Practice Set"

        diff_mix: DifficultyMix | None = None
        if payload.difficulty_progression == "easy_to_medium":
            easy_cnt = math.ceil(payload.question_count * 0.6)
            medium_cnt = max(0, payload.question_count - easy_cnt)
            diff_mix = DifficultyMix(easy=easy_cnt, medium=medium_cnt, hard=0)

        test_req = TestCreateRequest(
            title=title[:255],
            topic_ids=payload.topic_ids,
            question_count=payload.question_count,
            origin_mode="mixed",
            difficulty_mix=diff_mix,
            timer_mode=payload.timer_mode,
            per_question_seconds=payload.per_question_seconds,
            show_explanation_after=(
                "after_question" if payload.timer_mode == "learning_mode" else "after_submission"
            ),
        )
        try:
            test_out = self._test_builder.create_test(user_id, test_req)
        except TestBuildValidationError as exc:
            raise TargetedPracticeValidationError(str(exc)) from exc

        notes = self._repo.list_notes_for_topics(user_id, payload.topic_ids)
        linked_note_ids = [n.id for n in notes]
        return TargetedPracticeResponse(test=test_out, linked_note_ids=linked_note_ids)
