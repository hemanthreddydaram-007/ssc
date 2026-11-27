from __future__ import annotations

import re
from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assessment import Question
from app.models.learning import Topic
from app.schemas.notes import PYQPatternsOut, PYQSubjectStat, PYQTopicStat

_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_WS_RE = re.compile(r"\s+")


def _question_template_signature(stem: str) -> str:
    masked = _NUM_RE.sub("<N>", stem.lower())
    words = _WS_RE.sub(" ", masked).strip().split()
    return " ".join(words[:10])


def analyze_pyq_patterns(db: Session, document_id: UUID) -> PYQPatternsOut:
    """Compute sample-scoped PYQ pattern statistics with explicit denominators."""
    questions = list(
        db.execute(
            select(Question)
            .where(Question.document_id == document_id)
            .order_by(Question.source_page_number, Question.created_at)
        )
        .scalars()
        .all()
    )
    total = len(questions)
    if total == 0:
        return PYQPatternsOut(
            document_id=document_id,
            total_questions_analyzed=0,
            sample_note=(
                "No questions detected in this document yet (0 questions analyzed). "
                "Sample-scoped counts do not represent official exam weightage."
            ),
        )

    topic_ids = {q.topic_id for q in questions if q.topic_id is not None}
    topics_by_id: dict[UUID, Topic] = {}
    if topic_ids:
        for t in db.execute(select(Topic).where(Topic.id.in_(topic_ids))).scalars().all():
            topics_by_id[t.id] = t

    subject_counts: Counter[str] = Counter()
    topic_counts: Counter[tuple[UUID | None, str]] = Counter()
    difficulty_counts: Counter[str] = Counter()
    year_shift_counts: Counter[tuple[str, str]] = Counter()
    template_counts: Counter[str] = Counter()

    for q in questions:
        subject_counts[q.subject_code or "unknown"] += 1
        t_obj = topics_by_id.get(q.topic_id) if q.topic_id else None
        t_name = t_obj.name if t_obj is not None else "Uncategorized"
        topic_counts[(q.topic_id, t_name)] += 1
        difficulty_counts[q.difficulty or "medium"] += 1

        meta = q.pyq_metadata_json or {}
        if isinstance(meta, dict) and (meta.get("year") or meta.get("shift")):
            year_str = str(meta.get("year") or "unspecified")
            shift_str = str(meta.get("shift") or "unspecified")
            year_shift_counts[(year_str, shift_str)] += 1

        sig = _question_template_signature(q.question_text)
        if sig:
            template_counts[sig] += 1

    subjects = [
        PYQSubjectStat(
            subject_code=code,
            count=cnt,
            percentage=round(cnt * 100.0 / total, 1),
        )
        for code, cnt in subject_counts.most_common()
    ]
    topics = [
        PYQTopicStat(
            topic_id=tid,
            topic_name=tname,
            count=cnt,
            percentage=round(cnt * 100.0 / total, 1),
        )
        for (tid, tname), cnt in topic_counts.most_common()
    ]
    years_shifts: list[dict[str, Any]] = [
        {"year": yr, "shift": sh, "count": cnt}
        for (yr, sh), cnt in year_shift_counts.most_common()
    ]
    repeated_templates: list[dict[str, Any]] = [
        {"template": tpl, "count": cnt, "denominator": total}
        for tpl, cnt in template_counts.most_common(10)
        if cnt >= 2
    ]

    return PYQPatternsOut(
        document_id=document_id,
        total_questions_analyzed=total,
        sample_note=(
            f"Based on {total} question(s) detected in this uploaded document. "
            "Sample-scoped frequency reflects this file only, not official exam weightage."
        ),
        subjects=subjects,
        topics=topics,
        difficulty_distribution=dict(difficulty_counts),
        years_shifts=years_shifts,
        repeated_templates=repeated_templates,
    )
