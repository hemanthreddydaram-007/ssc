from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.ai.mock_provider import MockLLMProvider
from app.models.document import Document, DocumentChunk, DocumentPage
from app.models.user import User
from app.services.classification.classifier import DocumentClassifier
from app.services.classification.topic_mapper import TopicMapper
from app.services.knowledge.grounding import verify_grounding


def _create_user_and_doc(db: Session, *, subject_code: str | None = None) -> Document:
    user = User(id=uuid.uuid4(), display_name="Test Student")
    db.add(user)
    db.flush()
    doc = Document(
        id=uuid.uuid4(),
        user_id=user.id,
        title="SSC Practice Material",
        original_filename="ssc.pdf",
        source_type="pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        sha256="a" * 64,
        storage_key="users/u/doc/ssc.pdf",
        subject_code=subject_code,
        material_type="other",
        language="en",
        page_count=2,
        status="extracted",
    )
    db.add(doc)
    db.flush()
    return doc


def test_classifier_allows_unknown_and_preserves_user_override(db_session: Session) -> None:
    doc = _create_user_and_doc(db_session, subject_code=None)
    pages = [
        DocumentPage(
            document_id=doc.id,
            page_number=1,
            extracted_text="Lorem ipsum dolor sit amet unrelated text.",
            extraction_method="pymupdf",
            confidence=1.0,
            processing_status="done",
        )
    ]
    chunks = [
        DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            page_start=1,
            page_end=1,
            chunk_type="prose",
            content_text="Lorem ipsum dolor sit amet unrelated text.",
        )
    ]

    classifier = DocumentClassifier(db_session, MockLLMProvider())
    outcome = classifier.classify_document(doc, pages=pages, chunks=chunks)

    assert outcome.detected_subject_code == "unknown"
    assert outcome.effective_subject_code == "unknown"
    assert doc.subject_code == "unknown"

    # Now verify user-explicit subject_code is NOT overwritten by auto-detection
    doc_explicit = _create_user_and_doc(db_session, subject_code="english")
    maths_pages = [
        DocumentPage(
            document_id=doc_explicit.id,
            page_number=1,
            extracted_text="Percentage profit loss ratio algebra geometry.",
            extraction_method="pymupdf",
            confidence=1.0,
            processing_status="done",
        )
    ]
    maths_chunks = [
        DocumentChunk(
            document_id=doc_explicit.id,
            chunk_index=0,
            page_start=1,
            page_end=1,
            chunk_type="prose",
            content_text="Percentage profit loss ratio algebra geometry.",
        )
    ]
    outcome2 = classifier.classify_document(doc_explicit, pages=maths_pages, chunks=maths_chunks)
    assert outcome2.detected_subject_code == "quantitative_aptitude"
    assert doc_explicit.subject_code == "english"
    assert outcome2.effective_subject_code == "english"


def test_topic_mapper_maps_canonical_and_unknown_topics(db_session: Session) -> None:
    mapper = TopicMapper(db_session)

    t_exact = mapper.map_topic(subject_code="quantitative_aptitude", topic_name="Time and Work")
    assert t_exact is not None
    assert t_exact.is_canonical is True
    assert t_exact.slug == "time-and-work"

    t_fuzzy = mapper.map_topic(subject_code="quantitative_aptitude", topic_name="Profit & Loss")
    assert t_fuzzy is not None
    assert t_fuzzy.slug == "profit-and-loss"

    t_custom = mapper.map_topic(subject_code="unknown", topic_name="Custom Topic XYZ")
    assert t_custom is not None
    assert t_custom.is_canonical is False

    assert mapper.map_topic(subject_code="english", topic_name="unknown") is None
    assert mapper.map_topic(subject_code="english", topic_name="   ") is None


def test_grounding_verifies_excerpt_corrects_page_drift_and_rejects_bad_pages() -> None:
    pages_by_num = {
        1: "Page one covers Percentages: 10% equals 1/10 in fraction form.",
        2: "Page two covers Simple Interest: SI = (P * R * T) / 100.",
    }

    # Exact page match
    ok = verify_grounding(
        pages_by_num,
        claimed_page=1,
        page_start=1,
        page_end=2,
        supporting_excerpt="10% equals 1/10 in fraction form",
        claimed_provenance="extracted",
        confidence=0.9,
    )
    assert ok.is_grounded is True
    assert ok.resolved_page_number == 1
    assert ok.review_status == "verified"

    # Page drift inside multi-page chunk corrected from 1 -> 2
    drifted = verify_grounding(
        pages_by_num,
        claimed_page=1,
        page_start=1,
        page_end=2,
        supporting_excerpt="SI = (P * R * T) / 100",
        claimed_provenance="extracted",
        confidence=0.9,
    )
    assert drifted.is_grounded is True
    assert drifted.resolved_page_number == 2
    assert drifted.review_status == "verified"

    # Out-of-bounds page & fabricated excerpt -> cleared and flagged needs_review + unverified
    bogus = verify_grounding(
        pages_by_num,
        claimed_page=99,
        page_start=1,
        page_end=2,
        supporting_excerpt="Completely fabricated statement not on any page",
        claimed_provenance="extracted",
        confidence=0.95,
    )
    assert bogus.is_grounded is False
    assert bogus.resolved_page_number is None
    assert bogus.review_status == "needs_review"
    assert bogus.provenance == "unverified"
