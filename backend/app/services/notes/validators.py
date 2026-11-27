from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from rapidfuzz import fuzz

from app.ai.schemas.notes import GeneratedNoteOutput
from app.models.learning import Concept, Fact
from app.schemas.notes import NoteBlock, NoteContentJson, NoteSection, NoteSourceRef
from app.services.subjects.base import SubjectValidationReport
from app.services.subjects.registry import SUBJECT_ADAPTER_REGISTRY


@dataclass(slots=True)
class NoteValidationOutcome:
    """Validated note content plus derived review status and warnings."""

    content: NoteContentJson
    status: str
    warnings: list[str]
    subject_report: SubjectValidationReport


def content_text_length(content: NoteContentJson) -> int:
    """Measure total textual size of a note for quick-revision brevity enforcement."""
    parts = [content.summary]
    if content.one_minute_recap:
        parts.append(content.one_minute_recap)
    for section in content.sections:
        parts.append(section.title)
        for block in section.blocks:
            if block.title:
                parts.append(block.title)
            parts.append(block.body)
    return sum(len(p) for p in parts)


def _find_matching_source_ref(
    body: str,
    *,
    document_id: UUID,
    facts: list[Fact],
    concepts: list[Concept],
) -> NoteSourceRef | None:
    body_lower = " ".join(body.lower().split())
    for fact in facts:
        if fact.source_page_number is None:
            continue
        fact_lower = " ".join(fact.content.lower().split())
        if fuzz.partial_ratio(fact_lower, body_lower) >= 75.0:
            return NoteSourceRef(
                document_id=document_id,
                page_number=fact.source_page_number,
                supporting_excerpt=fact.supporting_excerpt or fact.content[:200],
            )
    for concept in concepts:
        refs = concept.source_refs_json or []
        if not refs:
            continue
        concept_lower = " ".join(concept.explanation.lower().split())
        if fuzz.partial_ratio(concept_lower, body_lower) >= 75.0 and isinstance(refs[0], dict):
            page_num = refs[0].get("page_number")
            if isinstance(page_num, int):
                return NoteSourceRef(
                    document_id=document_id,
                    page_number=page_num,
                    supporting_excerpt=str(refs[0].get("supporting_excerpt") or "")[:200],
                )
    return None


def validate_generated_note(
    generated: GeneratedNoteOutput,
    *,
    document_id: UUID,
    subject_code: str | None,
    note_type: str,
    facts: list[Fact],
    concepts: list[Concept],
    detailed_reference: NoteContentJson | None = None,
) -> NoteValidationOutcome:
    """Convert raw LLM note output into verified `NoteContentJson` with provenance & math checks."""
    valid_pages: set[int] = set()
    for f in facts:
        if f.source_page_number is not None:
            valid_pages.add(f.source_page_number)
    for c in concepts:
        for ref in c.source_refs_json or []:
            if isinstance(ref, dict) and isinstance(ref.get("page_number"), int):
                valid_pages.add(ref["page_number"])

    warnings: list[str] = []
    sections: list[NoteSection] = []

    for gen_section in generated.sections:
        blocks: list[NoteBlock] = []
        for gen_block in gen_section.blocks:
            metadata = {item.key: item.value for item in gen_block.metadata_items}
            refs: list[NoteSourceRef] = []
            for r in gen_block.source_refs:
                if r.page_number is not None and (not valid_pages or r.page_number in valid_pages):
                    refs.append(
                        NoteSourceRef(
                            document_id=document_id,
                            page_number=r.page_number,
                            supporting_excerpt=r.supporting_excerpt,
                        )
                    )

            provenance = gen_block.provenance
            review_status = gen_block.review_status

            if provenance in ("extracted", "paraphrased") and not refs:
                inferred = _find_matching_source_ref(
                    gen_block.body,
                    document_id=document_id,
                    facts=facts,
                    concepts=concepts,
                )
                if inferred is not None:
                    refs.append(inferred)
                else:
                    # Never present ungrounded/AI additions as extracted source facts.
                    provenance = "ai_explanation"
                    review_status = "needs_review"
                    warnings.append(
                        f"Section '{gen_section.key}' block downgraded to 'ai_explanation' "
                        "because no supporting source page citation matched stored records."
                    )

            blocks.append(
                NoteBlock(
                    block_type=gen_block.block_type,
                    title=gen_block.title,
                    body=gen_block.body,
                    formula_latex=gen_block.formula_latex,
                    metadata=metadata,
                    provenance=provenance,
                    source_refs=refs,
                    review_status=review_status,
                )
            )
        sections.append(NoteSection(key=gen_section.key, title=gen_section.title, blocks=blocks))

    content = NoteContentJson(
        summary=generated.summary,
        sections=sections,
        one_minute_recap=generated.one_minute_recap,
    )

    # Enforce quick_revision brevity relative to detailed notes when present.
    if note_type == "quick_revision" and detailed_reference is not None:
        detailed_len = content_text_length(detailed_reference)
        if detailed_len > 0 and content_text_length(content) >= detailed_len:
            # Trim excess blocks from quick_revision while preserving recap & first key block.
            for sec in content.sections:
                sec.blocks = sec.blocks[:1]
                for blk in sec.blocks:
                    if len(blk.body) > 220:
                        blk.body = blk.body[:217].rstrip() + "..."
            content.sections = content.sections[:2]

    adapter = SUBJECT_ADAPTER_REGISTRY.get(subject_code)
    subject_report = adapter.validate_note_content(
        content,
        source_facts=facts,
        source_concepts=concepts,
    )
    warnings.extend(subject_report.warnings)

    has_needs_review = subject_report.needs_review or any(
        blk.review_status in ("needs_review", "conflict")
        for sec in content.sections
        for blk in sec.blocks
    )
    note_status = "needs_review" if has_needs_review else "ready"
    return NoteValidationOutcome(
        content=content,
        status=note_status,
        warnings=warnings,
        subject_report=subject_report,
    )
