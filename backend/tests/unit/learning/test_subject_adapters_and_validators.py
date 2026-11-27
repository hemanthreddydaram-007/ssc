from __future__ import annotations

import uuid

from app.ai.schemas.notes import (
    GeneratedNoteBlock,
    GeneratedNoteOutput,
    GeneratedNoteSection,
    GeneratedSourceRefItem,
)
from app.models.learning import Fact
from app.services.notes.validators import content_text_length, validate_generated_note
from app.services.subjects.maths import verify_numeric_equations
from app.services.subjects.registry import SUBJECT_ADAPTER_REGISTRY


def test_sympy_numeric_verification_catches_wrong_maths_equations() -> None:
    assert verify_numeric_equations("Profit = 250 - 200 = 50. Also 25% of 200 = 50.") == []

    bad = verify_numeric_equations("Shortcut example: 250 - 200 = 99 and 20% of 200 = 80.")
    assert len(bad) == 2


def test_maths_adapter_flags_wrong_worked_example_as_needs_review() -> None:
    doc_id = uuid.uuid4()
    fact = Fact(
        id=uuid.uuid4(),
        document_id=doc_id,
        fact_type="formula",
        content="Profit = SP - CP",
        provenance="extracted",
        confidence=0.9,
        source_page_number=1,
        supporting_excerpt="Profit = SP - CP",
        review_status="verified",
    )
    generated = GeneratedNoteOutput(
        title="Profit and Loss Strategy",
        summary="Maths solving methods",
        sections=[
            GeneratedNoteSection(
                key="worked_examples",
                title="Worked Examples",
                blocks=[
                    GeneratedNoteBlock(
                        block_type="worked_example",
                        title="Bad Arithmetic",
                        body="Step 1: 250 - 200 = 80, so profit percentage = 40%.",
                        provenance="ai_explanation",
                    )
                ],
            )
        ],
    )

    outcome = validate_generated_note(
        generated,
        document_id=doc_id,
        subject_code="quantitative_aptitude",
        note_type="strategy_sheet",
        facts=[fact],
        concepts=[],
    )

    assert outcome.status == "needs_review"
    assert outcome.subject_report.needs_review is True
    blk = outcome.content.sections[0].blocks[0]
    assert blk.review_status == "needs_review"
    assert "math_verification_warnings" in blk.metadata


def test_general_awareness_adapter_flags_time_sensitive_facts() -> None:
    doc_id = uuid.uuid4()
    fact = Fact(
        id=uuid.uuid4(),
        document_id=doc_id,
        fact_type="person",
        content="Current Governor of RBI is Shaktikanta Das.",
        provenance="extracted",
        confidence=0.9,
        source_page_number=3,
        supporting_excerpt="Current Governor of RBI",
        is_time_sensitive=True,
        source_date_label="2024",
        review_status="verified",
    )
    generated = GeneratedNoteOutput(
        title="Current Affairs",
        summary="Banking updates",
        sections=[
            GeneratedNoteSection(
                key="facts",
                title="Key Facts",
                blocks=[
                    GeneratedNoteBlock(
                        block_type="definition",
                        body="Current Governor of RBI is Shaktikanta Das.",
                        provenance="extracted",
                        source_refs=[
                            GeneratedSourceRefItem(
                                page_number=3, supporting_excerpt="Current Governor of RBI"
                            )
                        ],
                    )
                ],
            )
        ],
    )

    outcome = validate_generated_note(
        generated,
        document_id=doc_id,
        subject_code="general_awareness",
        note_type="detailed",
        facts=[fact],
        concepts=[],
    )

    keys = [sec.key for sec in outcome.content.sections]
    assert "staleness_notice" in keys
    assert outcome.status == "needs_review"


def test_validator_downgrades_ungrounded_extracted_claim_and_enforces_quick_brevity() -> None:
    doc_id = uuid.uuid4()
    fact = Fact(
        id=uuid.uuid4(),
        document_id=doc_id,
        fact_type="rule",
        content="A singular subject takes a singular verb.",
        provenance="extracted",
        confidence=0.9,
        source_page_number=1,
        supporting_excerpt="singular subject takes a singular verb",
        review_status="verified",
    )

    detailed = GeneratedNoteOutput(
        title="Detailed",
        summary="Detailed grammar overview covering every nuance and worked example.",
        sections=[
            GeneratedNoteSection(
                key="core",
                title="Core Grammar Rules",
                blocks=[
                    GeneratedNoteBlock(
                        block_type="rule",
                        body=(
                            "A singular subject takes a singular verb. "
                            + ("Extra context. " * 15)
                        ),
                        provenance="extracted",
                        source_refs=[
                            GeneratedSourceRefItem(
                                page_number=1,
                                supporting_excerpt="singular subject takes a singular verb",
                            )
                        ],
                    ),
                    GeneratedNoteBlock(
                        block_type="definition",
                        body="Completely unrelated ungrounded claim about cosmic rays.",
                        provenance="extracted",
                        source_refs=[],
                    ),
                ],
            )
        ],
    )
    detailed_outcome = validate_generated_note(
        detailed,
        document_id=doc_id,
        subject_code="english",
        note_type="detailed",
        facts=[fact],
        concepts=[],
    )
    # Ungrounded block downgraded to ai_explanation + needs_review
    downgraded = detailed_outcome.content.sections[0].blocks[1]
    assert downgraded.provenance == "ai_explanation"
    assert downgraded.review_status == "needs_review"

    # Quick revision made longer than detailed must be trimmed strictly shorter
    bloated_quick = GeneratedNoteOutput(
        title="Quick",
        summary="Quick revision summary.",
        sections=[
            GeneratedNoteSection(
                key="s1",
                title="Section 1",
                blocks=[
                    GeneratedNoteBlock(
                        block_type="recap",
                        body="Long recap text. " * 40,
                        provenance="ai_explanation",
                    ),
                    GeneratedNoteBlock(
                        block_type="recap",
                        body="Second block. " * 20,
                        provenance="ai_explanation",
                    ),
                ],
            )
        ],
        one_minute_recap="Short 1-minute recap.",
    )
    quick_outcome = validate_generated_note(
        bloated_quick,
        document_id=doc_id,
        subject_code="english",
        note_type="quick_revision",
        facts=[fact],
        concepts=[],
        detailed_reference=detailed_outcome.content,
    )
    assert content_text_length(quick_outcome.content) < content_text_length(
        detailed_outcome.content
    )


def test_all_four_subject_adapters_registered() -> None:
    caps = {c.subject_code for c in SUBJECT_ADAPTER_REGISTRY.list_capabilities()}
    assert caps == {
        "quantitative_aptitude",
        "reasoning",
        "english",
        "general_awareness",
    }
    assert SUBJECT_ADAPTER_REGISTRY.get("unknown").subject_code == "unknown"
