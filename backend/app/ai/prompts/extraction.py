from __future__ import annotations

from app.ai.prompts.registry import PROMPT_REGISTRY, PromptTemplate

KNOWLEDGE_EXTRACTION_PROMPT_V1 = PROMPT_REGISTRY.register(
    PromptTemplate(
        name="knowledge_extraction",
        version="v1",
        system_instruction=(
            "You extract structured study knowledge from document chunks into strict JSON. "
            "Rules:\n"
            "1. Only extract facts, concepts, formulas, rules, and questions supported "
            "by the chunk.\n"
            "2. Preserve exact [PAGE N] citations in source_page_number and copy a short verbatim "
            "supporting_excerpt from the chunk text.\n"
            "3. Never fabricate answer keys; if a question has no answer key in the source, set "
            "correct_option_key to null and answer_key_provenance to 'unverified'.\n"
            "4. For General Awareness / Current Affairs facts that depend on time (officeholders, "
            "rankings, schemes, current events), set is_time_sensitive=true and capture "
            "source_date_label if stated.\n"
            "5. Use 'unknown' if the subject is ambiguous."
        ),
        user_template=(
            "Extract topics, facts, concepts, and any exam questions from this chunk.\n"
            "Subject context: {subject_code}\n"
            "Exam context: {exam_code}\n"
            "Page range: {page_start}-{page_end}\n"
            "Section title: {section_title}\n"
            "Canonical topic hints: {topic_hints}\n\n"
            "Chunk text:\n{chunk_text}"
        ),
    )
)

QUESTION_VERIFICATION_PROMPT_V1 = PROMPT_REGISTRY.register(
    PromptTemplate(
        name="question_verify",
        version="v1",
        system_instruction=(
            "You verify whether a multiple-choice question has one unambiguous correct answer "
            "and distinct distractors grounded in the provided evidence."
        ),
        user_template=(
            "Verify the following question against the supplied evidence.\n"
            "Question JSON:\n{question_json}\n\n"
            "Evidence:\n{evidence_text}"
        ),
    )
)
