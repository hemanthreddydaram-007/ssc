from __future__ import annotations

import logging

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.user import ExamConfig, User

logger = logging.getLogger(__name__)


def seed_defaults(db: Session, settings: Settings) -> None:
    """Seed local default user and SSC CHSL Tier 1 exam pack if tables exist."""
    inspector = inspect(db.bind)
    if not inspector.has_table("users") or not inspector.has_table("exam_configs"):
        return

    user = db.get(User, settings.local_default_user_id)
    if user is None:
        db.add(
            User(
                id=settings.local_default_user_id,
                display_name=settings.local_default_user_name,
            )
        )

    existing_exam = db.query(ExamConfig).filter(ExamConfig.exam_code == "ssc_chsl_tier_1").first()
    if existing_exam is None:
        db.add(
            ExamConfig(
                exam_code="ssc_chsl_tier_1",
                name="SSC CHSL Tier 1",
                version="1.0",
                config_json={
                    "exam_code": "ssc_chsl_tier_1",
                    "display_name": "SSC CHSL Tier 1",
                    "subjects": [
                        "quantitative_aptitude",
                        "reasoning",
                        "english",
                        "general_awareness",
                    ],
                    "question_types": ["single_choice"],
                    "supports_negative_marking": True,
                    "timing_mode": ["speed_challenge", "exam_simulation", "learning_mode"],
                    "default_speed_challenge_seconds": 35,
                    "notes": "Verify official SSC notification before publishing fixed exam rules.",
                },
            )
        )
    db.commit()
