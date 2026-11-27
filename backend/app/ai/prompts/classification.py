from __future__ import annotations

from app.ai.prompts.registry import PROMPT_REGISTRY, PromptTemplate

CLASSIFICATION_PROMPT_V1 = PROMPT_REGISTRY.register(
    PromptTemplate(
        name="document_classification",
        version="v1",
        system_instruction=(
            "You are a precise curriculum and exam-material classifier for competitive exams "
            "(starting with SSC CHSL Tier 1: quantitative_aptitude, reasoning, english, "
            "general_awareness). Classify strictly from the provided sample text. "
            "If the subject is mixed, unclear, or outside the known subjects, return 'unknown' "
            "instead of guessing."
        ),
        user_template=(
            "Classify the following study material excerpt.\n"
            "Document title: {title}\n"
            "User-provided subject hint: {subject_hint}\n"
            "User-provided material type hint: {material_type_hint}\n"
            "Exam code: {exam_code}\n\n"
            "Sample text:\n{sample_text}"
        ),
    )
)
