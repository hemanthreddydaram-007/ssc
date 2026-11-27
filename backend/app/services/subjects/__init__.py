from app.services.subjects.base import SubjectAdapter, SubjectValidationReport
from app.services.subjects.english import EnglishSubjectAdapter
from app.services.subjects.general_awareness import GeneralAwarenessSubjectAdapter
from app.services.subjects.maths import MathsSubjectAdapter, verify_numeric_equations
from app.services.subjects.reasoning import ReasoningSubjectAdapter
from app.services.subjects.registry import (
    SUBJECT_ADAPTER_REGISTRY,
    DefaultSubjectAdapter,
    SubjectAdapterRegistry,
)

__all__ = [
    "DefaultSubjectAdapter",
    "EnglishSubjectAdapter",
    "GeneralAwarenessSubjectAdapter",
    "MathsSubjectAdapter",
    "SUBJECT_ADAPTER_REGISTRY",
    "SubjectAdapter",
    "SubjectAdapterRegistry",
    "SubjectValidationReport",
    "ReasoningSubjectAdapter",
    "verify_numeric_equations",
]
