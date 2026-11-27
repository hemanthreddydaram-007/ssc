from __future__ import annotations

from app.schemas.topics import SubjectCapabilityOut
from app.services.subjects.base import SubjectAdapter
from app.services.subjects.english import EnglishSubjectAdapter
from app.services.subjects.general_awareness import GeneralAwarenessSubjectAdapter
from app.services.subjects.maths import MathsSubjectAdapter
from app.services.subjects.reasoning import ReasoningSubjectAdapter


class DefaultSubjectAdapter(SubjectAdapter):
    """Fallback adapter for `unknown` or newly added subjects."""

    def __init__(self, subject_code: str = "unknown") -> None:
        self.subject_code = subject_code
        self.display_name = (
            "General / Unclassified"
            if subject_code == "unknown"
            else subject_code.replace("_", " ").title()
        )
        self.supported_strategies = ["core_concepts", "worked_examples", "common_traps"]

    def strategy_instructions(self) -> str:
        return (
            "Provide a clear step-by-step solving procedure, worked examples grounded in stored "
            "records, and common mistakes/traps to avoid."
        )


class SubjectAdapterRegistry:
    """Registry resolving subject codes to specialized `SubjectAdapter` instances."""

    def __init__(self) -> None:
        self._adapters: dict[str, SubjectAdapter] = {}
        for adapter in (
            MathsSubjectAdapter(),
            ReasoningSubjectAdapter(),
            EnglishSubjectAdapter(),
            GeneralAwarenessSubjectAdapter(),
        ):
            self.register(adapter)

    def register(self, adapter: SubjectAdapter) -> None:
        self._adapters[adapter.subject_code] = adapter

    def get(self, subject_code: str | None) -> SubjectAdapter:
        if subject_code and subject_code in self._adapters:
            return self._adapters[subject_code]
        return DefaultSubjectAdapter(subject_code or "unknown")

    def list_capabilities(self) -> list[SubjectCapabilityOut]:
        return [
            SubjectCapabilityOut(
                subject_code=a.subject_code,
                display_name=a.display_name,
                supported_strategies=list(a.supported_strategies),
            )
            for a in self._adapters.values()
        ]


SUBJECT_ADAPTER_REGISTRY = SubjectAdapterRegistry()
