"""Coverage audit: deterministic report from DB page/chunk/knowledge records.

Never calls an LLM. Reads database aggregates and returns a CoverageAuditOut.
Does not claim 100% coverage.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import DocumentAsset, DocumentChunk, DocumentPage
from app.models.learning import Concept, Fact
from app.schemas.job import CoverageAuditOut, LowConfidencePageOut

LOW_CONFIDENCE_THRESHOLD = 0.5
SKIPPED_STATUSES = {"not_processed", "failed"}


def build_coverage_audit(db: Session, document_id: UUID) -> CoverageAuditOut:
    """Compute a deterministic coverage audit from DB records without any LLM calls."""
    pages = (
        db.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        )
        .scalars()
        .all()
    )

    total_pages = len(pages)
    pages_extracted_text = 0
    pages_extracted_ocr = 0
    pages_requiring_ocr = 0
    pages_not_processed = 0
    tables_extracted = 0
    low_confidence_pages: list[LowConfidencePageOut] = []

    for p in pages:
        status = p.processing_status or "pending"
        has_real_ocr = bool(p.ocr_provider and p.ocr_provider != "null")
        if status in SKIPPED_STATUSES:
            pages_not_processed += 1
        elif has_real_ocr and status == "done":
            pages_extracted_ocr += 1
        elif p.needs_ocr:
            pages_requiring_ocr += 1
        else:
            pages_extracted_text += 1

        tables_extracted += p.table_count or 0

        if (p.confidence or 0.0) < LOW_CONFIDENCE_THRESHOLD or (
            p.needs_ocr and not has_real_ocr
        ):
            low_confidence_pages.append(
                LowConfidencePageOut(
                    page_number=p.page_number,
                    confidence=p.confidence or 0.0,
                    extraction_method=p.extraction_method or "unknown",
                    warning=p.warning,
                )
            )

    images_extracted = int(
        db.execute(
            select(func.count()).select_from(DocumentAsset).where(
                DocumentAsset.document_id == document_id
            )
        ).scalar_one()
    )

    chunks_created = int(
        db.execute(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        ).scalar_one()
    )

    facts_extracted = int(
        db.execute(
            select(func.count()).select_from(Fact).where(Fact.document_id == document_id)
        ).scalar_one()
    )

    concepts_identified = int(
        db.execute(
            select(func.count()).select_from(Concept).where(Concept.document_id == document_id)
        ).scalar_one()
    )

    # Questions extracted: check questions table if exists (gracefully handle missing table)
    try:
        from app.models.assessment import Question  # noqa: PLC0415

        questions_extracted = int(
            db.execute(
                select(func.count()).select_from(Question).where(
                    Question.document_id == document_id
                )
            ).scalar_one()
        )
    except Exception:
        questions_extracted = 0

    # Records rejected/uncertain: facts or concepts with needs_review or conflict status
    try:
        from app.models.learning import Fact as FactModel  # noqa: PLC0415

        rejected_facts = int(
            db.execute(
                select(func.count()).select_from(FactModel).where(
                    FactModel.document_id == document_id,
                    FactModel.review_status.in_(["needs_review", "conflict", "rejected"]),
                )
            ).scalar_one()
        )
    except Exception:
        rejected_facts = 0

    return CoverageAuditOut(
        document_id=document_id,
        total_pages=total_pages,
        pages_extracted_text=pages_extracted_text,
        pages_extracted_ocr=pages_extracted_ocr,
        pages_requiring_ocr=pages_requiring_ocr,
        pages_not_processed=pages_not_processed,
        low_confidence_pages=low_confidence_pages,
        tables_extracted=tables_extracted,
        images_extracted=images_extracted,
        chunks_created=chunks_created,
        facts_extracted=facts_extracted,
        concepts_identified=concepts_identified,
        questions_extracted=questions_extracted,
        records_rejected_or_uncertain=rejected_facts,
        low_confidence_topics=[],  # populated after classification in M3+
    )


def build_coverage_summary(
    *,
    total_pages: int,
    pages_extracted_text: int,
    pages_extracted_ocr: int,
    pages_requiring_ocr: int,
    pages_not_processed: int,
    tables_extracted: int,
    images_extracted: int,
    chunks_created: int,
    facts_extracted: int = 0,
    concepts_identified: int = 0,
    questions_extracted: int = 0,
    records_rejected_or_uncertain: int = 0,
    low_confidence_pages: list[dict[str, Any]] | None = None,
    low_confidence_topics: list[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic coverage summary dictionary from real counts."""
    processed_pages = pages_extracted_text + pages_extracted_ocr
    progress_percent: int | None = None
    if total_pages > 0:
        progress_percent = int(min(100, round(processed_pages * 100 / total_pages)))

    return {
        "total_pages": total_pages,
        "pages_extracted_text": pages_extracted_text,
        "pages_extracted_ocr": pages_extracted_ocr,
        "pages_requiring_ocr": pages_requiring_ocr,
        "pages_not_processed": pages_not_processed,
        "low_confidence_pages": low_confidence_pages or [],
        "tables_extracted": tables_extracted,
        "images_extracted": images_extracted,
        "chunks_created": chunks_created,
        "facts_extracted": facts_extracted,
        "concepts_identified": concepts_identified,
        "questions_extracted": questions_extracted,
        "records_rejected_or_uncertain": records_rejected_or_uncertain,
        "low_confidence_topics": low_confidence_topics or [],
        "progress_percent": progress_percent,
    }
