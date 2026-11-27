from __future__ import annotations

from app.services.subjects.base import SubjectAdapter


class ReasoningSubjectAdapter(SubjectAdapter):
    """Subject adapter for General Intelligence / Reasoning (Section 3.2.C)."""

    subject_code = "reasoning"
    display_name = "General Intelligence / Reasoning"
    supported_strategies = [
        "pattern_recognition",
        "solving_procedure",
        "diagram_notation",
        "shortcut_failure_cases",
    ]

    def strategy_instructions(self) -> str:
        return (
            "Structure sections for Reasoning:\n"
            "1. pattern_relationship: Exact pattern or logical relationship being tested.\n"
            "2. solving_procedure: Reliable step-by-step solving procedure with diagram/table/"
            "notation description where helpful.\n"
            "3. recognition_cues_and_limits: Faster recognition cues AND explicit cases where "
            "a shortcut fails.\n"
            "4. worked_examples: Worked examples demonstrating the procedure."
        )
