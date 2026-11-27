from __future__ import annotations

from app.ai.prompts.registry import PROMPT_REGISTRY, PromptTemplate

STRATEGY_SHEET_PROMPT_V1 = PROMPT_REGISTRY.register(
    PromptTemplate(
        name="notes_strategy_sheet",
        version="v1",
        system_instruction=(
            "You generate a subject-specialized solving strategy sheet strictly grounded in the "
            "supplied concepts, facts, and representative questions. Follow the subject-specific "
            "template instructions carefully, clearly label shortcuts' assumptions and failure "
            "cases, mark any time comparisons as estimates, and distinguish 'ai_explanation' "
            "blocks from 'extracted'/'paraphrased' facts."
        ),
        user_template=(
            "Generate a subject-specific solving strategy sheet for topic '{topic_name}' "
            "(subject: {subject_code}).\n"
            "Subject template requirements:\n{subject_template_instructions}\n\n"
            "Stored knowledge records:\n{knowledge_records_json}"
        ),
    )
)
