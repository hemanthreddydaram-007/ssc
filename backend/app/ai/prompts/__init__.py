from app.ai.prompts.classification import CLASSIFICATION_PROMPT_V1
from app.ai.prompts.extraction import (
    KNOWLEDGE_EXTRACTION_PROMPT_V1,
    QUESTION_VERIFICATION_PROMPT_V1,
)
from app.ai.prompts.notes import (
    DETAILED_NOTES_PROMPT_V1,
    FORMULA_SHEET_PROMPT_V1,
    NOTE_REGENERATE_PROMPT_V1,
    QUICK_REVISION_PROMPT_V1,
)
from app.ai.prompts.registry import PROMPT_REGISTRY, PromptRegistry, PromptTemplate
from app.ai.prompts.strategies import STRATEGY_SHEET_PROMPT_V1

__all__ = [
    "CLASSIFICATION_PROMPT_V1",
    "DETAILED_NOTES_PROMPT_V1",
    "FORMULA_SHEET_PROMPT_V1",
    "KNOWLEDGE_EXTRACTION_PROMPT_V1",
    "NOTE_REGENERATE_PROMPT_V1",
    "PROMPT_REGISTRY",
    "QUESTION_VERIFICATION_PROMPT_V1",
    "QUICK_REVISION_PROMPT_V1",
    "STRATEGY_SHEET_PROMPT_V1",
    "PromptRegistry",
    "PromptTemplate",
]
