from __future__ import annotations

from app.ai.prompts.registry import PROMPT_REGISTRY, PromptTemplate

DETAILED_NOTES_PROMPT_V1 = PROMPT_REGISTRY.register(
    PromptTemplate(
        name="notes_detailed",
        version="v1",
        system_instruction=(
            "You generate structured, source-grounded detailed smart notes strictly from the "
            "supplied validated knowledge records (concepts, facts, formulas, and representative "
            "questions). Rules:\n"
            "1. Cover: learning objective, simple definition, why it matters, step-by-step "
            "explanation, worked examples, key facts/formulas/rules/dates, common misconceptions "
            "and traps, representative questions, exam relevance (ONLY if supported by supplied "
            "PYQs or exam config), and source references.\n"
            "2. Tag every block's provenance accurately: 'extracted' or 'paraphrased' ONLY when "
            "backed by supplied records with page_number and supporting_excerpt; use "
            "'ai_explanation' for any pedagogical framing or added worked explanation.\n"
            "3. Never fabricate statistics, official exam weightage, or missing citations."
        ),
        user_template=(
            "Generate detailed smart notes for topic '{topic_name}' (subject: {subject_code}).\n"
            "Exam context: {exam_context}\n"
            "Recommended section blueprint: {section_blueprint}\n\n"
            "Stored knowledge records:\n{knowledge_records_json}"
        ),
    )
)

QUICK_REVISION_PROMPT_V1 = PROMPT_REGISTRY.register(
    PromptTemplate(
        name="notes_quick_revision",
        version="v1",
        system_instruction=(
            "You generate genuinely concise, high-yield quick-revision notes strictly from the "
            "supplied knowledge records. Keep output substantially shorter than detailed notes. "
            "Include key facts, formula/rule sheet, crisp definitions, important comparisons, "
            "frequently confused points, mnemonics only when accurate, and a 1-minute recap. "
            "Label extracted/paraphrased source blocks separately from 'ai_explanation' blocks."
        ),
        user_template=(
            "Generate compact quick-revision notes for topic '{topic_name}' "
            "(subject: {subject_code}).\n"
            "Stored knowledge records:\n{knowledge_records_json}"
        ),
    )
)

FORMULA_SHEET_PROMPT_V1 = PROMPT_REGISTRY.register(
    PromptTemplate(
        name="notes_formula_sheet",
        version="v1",
        system_instruction=(
            "You generate a structured formula, rule, and key-fact reference sheet strictly from "
            "the supplied knowledge records. Include formula_latex where appropriate, exact "
            "assumptions/conditions, and verified source_refs."
        ),
        user_template=(
            "Generate a formula/rule reference sheet for topic '{topic_name}' "
            "(subject: {subject_code}).\n"
            "Stored knowledge records:\n{knowledge_records_json}"
        ),
    )
)

NOTE_REGENERATE_PROMPT_V1 = PROMPT_REGISTRY.register(
    PromptTemplate(
        name="notes_regenerate",
        version="v1",
        system_instruction=(
            "You regenerate selected note sections (or the full topic note) strictly from the "
            "supplied stored knowledge records without inventing facts. Preserve provenance "
            "distinction between source-backed records and 'ai_explanation' additions."
        ),
        user_template=(
            "Regenerate note type '{note_type}' for topic '{topic_name}' "
            "(subject: {subject_code}).\n"
            "Target section keys (empty = all): {section_keys}\n"
            "User instruction: {custom_instruction}\n"
            "Subject guidance: {subject_guidance}\n\n"
            "Stored knowledge records:\n{knowledge_records_json}"
        ),
    )
)
