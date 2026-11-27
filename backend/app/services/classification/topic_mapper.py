from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from app.models.learning import Topic
from app.repositories.knowledge_repo import KnowledgeRepository
from app.schemas.topics import SubjectCapabilityOut

SUBJECT_CATALOG: list[SubjectCapabilityOut] = [
    SubjectCapabilityOut(
        subject_code="quantitative_aptitude",
        display_name="Quantitative Aptitude / Maths",
        supported_strategies=[
            "standard_method",
            "alternative_method",
            "shortcut_with_assumptions",
            "calculation_traps",
        ],
    ),
    SubjectCapabilityOut(
        subject_code="reasoning",
        display_name="General Intelligence / Reasoning",
        supported_strategies=[
            "pattern_recognition",
            "solving_procedure",
            "diagram_notation",
            "shortcut_failure_cases",
        ],
    ),
    SubjectCapabilityOut(
        subject_code="english",
        display_name="English Language",
        supported_strategies=[
            "exact_grammar_rule",
            "correct_vs_incorrect_examples",
            "vocabulary_usage",
            "elimination_logic",
        ],
    ),
    SubjectCapabilityOut(
        subject_code="general_awareness",
        display_name="General Awareness",
        supported_strategies=[
            "five_ws_summary",
            "factual_tables",
            "timeline_sequence",
            "static_vs_current_flagging",
        ],
    ),
]

CANONICAL_TOPICS: dict[str, tuple[str, ...]] = {
    "quantitative_aptitude": (
        "Percentages",
        "Profit and Loss",
        "Ratio and Proportion",
        "Time and Work",
        "Time, Speed and Distance",
        "Simple and Compound Interest",
        "Averages",
        "Number System",
        "Algebra",
        "Geometry",
        "Mensuration",
        "Trigonometry",
        "Data Interpretation",
    ),
    "reasoning": (
        "Analogy",
        "Classification",
        "Number and Letter Series",
        "Coding-Decoding",
        "Syllogism",
        "Blood Relations",
        "Direction Sense",
        "Seating Arrangement",
        "Mirror and Water Images",
        "Venn Diagrams",
    ),
    "english": (
        "Subject-Verb Agreement",
        "Tenses",
        "Prepositions",
        "Active and Passive Voice",
        "Direct and Indirect Speech",
        "Error Spotting",
        "Synonyms and Antonyms",
        "Idioms and Phrases",
        "One-Word Substitution",
        "Reading Comprehension",
        "Cloze Test",
    ),
    "general_awareness": (
        "Indian Polity and Constitution",
        "Indian History",
        "Geography",
        "Indian Economy",
        "General Science",
        "Current Affairs",
        "Static GK",
        "Awards and Honours",
        "Books and Authors",
    ),
}

_UNKNOWN_TOPIC_MARKERS = {"", "unknown", "uncategorized", "none", "n/a", "general", "misc"}


def slugify_topic(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:120] or "unknown-topic"


@dataclass(slots=True)
class TopicMapper:
    """Maps extracted topic strings onto canonical or document-discovered `Topic` records."""

    db: Session
    exam_config_id: UUID | None = None
    repo: KnowledgeRepository = field(init=False)

    def __post_init__(self) -> None:
        self.repo = KnowledgeRepository(self.db)

    def ensure_canonical_topics(self, subject_code: str) -> list[Topic]:
        """Seed canonical syllabus topics lazily for a subject when first mapped."""
        names = CANONICAL_TOPICS.get(subject_code, ())
        topics: list[Topic] = []
        for idx, name in enumerate(names):
            topic = self.repo.get_or_create_topic(
                subject_code=subject_code,
                name=name,
                slug=slugify_topic(name),
                exam_config_id=self.exam_config_id,
                is_canonical=True,
                sort_order=idx + 1,
            )
            topics.append(topic)
        return topics

    def map_topic(self, *, subject_code: str, topic_name: str | None) -> Topic | None:
        """Resolve `topic_name` to a `Topic`, returning `None` for unknown/blank topics."""
        if topic_name is None:
            return None
        cleaned = " ".join(topic_name.split()).strip()
        if cleaned.lower() in _UNKNOWN_TOPIC_MARKERS:
            return None

        effective_subject = subject_code.strip() if subject_code else "unknown"
        if not effective_subject:
            effective_subject = "unknown"

        canonical_list = self.ensure_canonical_topics(effective_subject)
        if canonical_list:
            choices = {t.name: t for t in canonical_list}
            match_query = " ".join(cleaned.replace("&", " and ").split())
            match = process.extractOne(
                match_query,
                list(choices.keys()),
                scorer=fuzz.token_sort_ratio,
                score_cutoff=84,
            )
            if match is not None:
                return choices[match[0]]

        slug = slugify_topic(cleaned)
        return self.repo.get_or_create_topic(
            subject_code=effective_subject,
            name=cleaned,
            slug=slug,
            exam_config_id=self.exam_config_id,
            is_canonical=False,
            sort_order=100,
        )
