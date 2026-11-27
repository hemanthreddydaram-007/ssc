from __future__ import annotations

from app.services.subjects.base import SubjectAdapter


class EnglishSubjectAdapter(SubjectAdapter):
    """Subject adapter for English Language (Section 3.2.C)."""

    subject_code = "english"
    display_name = "English Language"
    supported_strategies = [
        "exact_grammar_rule",
        "correct_vs_incorrect_examples",
        "vocabulary_usage",
        "elimination_logic",
    ]

    def strategy_instructions(self) -> str:
        return (
            "Structure sections for English Language:\n"
            "1. grammar_rules: Exact grammar rule(s) with clear correct vs. incorrect examples.\n"
            "2. vocabulary_usage: Key vocabulary with meaning, nuance, and sentence usage.\n"
            "3. elimination_and_traps: Option-elimination logic and common exam traps.\n"
            "4. context_practice: Practice items applying the same rule in new contexts."
        )
