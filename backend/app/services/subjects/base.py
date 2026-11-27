from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.learning import Concept, Fact
from app.schemas.notes import NoteContentJson


@dataclass(slots=True)
class SubjectValidationReport:
    """Result of subject-specific post-generation checks on note content."""

    warnings: list[str] = field(default_factory=list)
    flagged_block_count: int = 0

    @property
    def needs_review(self) -> bool:
        return self.flagged_block_count > 0


class SubjectAdapter(ABC):
    """Base contract for subject-specialized note templates and validation."""

    subject_code: str
    display_name: str
    supported_strategies: list[str]

    def detailed_section_blueprint(self) -> list[tuple[str, str]]:
        """Ordered `(key, title)` blueprint for detailed smart notes."""
        return [
            ("learning_objective", "Learning Objective & Why It Matters"),
            ("core_concepts", "Core Concept & Step-by-Step Explanation"),
            ("worked_examples", "Worked Examples"),
            ("key_facts", "Important Facts, Formulas & Rules"),
            ("misconceptions", "Common Misconceptions & Traps"),
            ("representative_questions", "Representative Questions & Exam Relevance"),
        ]

    @abstractmethod
    def strategy_instructions(self) -> str:
        """Return subject-specific instructions for solving strategy sheets."""

    def validate_note_content(
        self,
        content: NoteContentJson,
        *,
        source_facts: list[Fact],
        source_concepts: list[Concept],
    ) -> SubjectValidationReport:
        """Run optional deterministic domain checks on generated note blocks."""
        return SubjectValidationReport()
