from __future__ import annotations

import uuid
from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.api.v1 import jobs, knowledge, topics
from app.db.session import get_db
from app.models.document import Document, DocumentChunk, DocumentPage
from app.models.user import User


def _make_test_client(
    db_engine: Engine,
    provider: MockLLMProvider,
) -> TestClient:
    session_factory = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    app = FastAPI()
    app.include_router(topics.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(jobs.router, prefix="/api/v1")

    def _override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app)


def _create_doc(
    db: Session,
    *,
    user_id: uuid.UUID,
    with_pages: bool = True,
) -> Document:
    if db.get(User, user_id) is None:
        db.add(User(id=user_id, display_name="User"))
        db.flush()

    doc = Document(
        id=uuid.uuid4(),
        user_id=user_id,
        title="SSC English Grammar Notes",
        original_filename="english.pdf",
        source_type="pdf",
        mime_type="application/pdf",
        file_size_bytes=2048,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_key="users/u/doc/english.pdf",
        material_type="notes",
        language="en",
        page_count=1 if with_pages else 0,
        status="extracted" if with_pages else "uploaded",
    )
    db.add(doc)
    db.flush()

    if with_pages:
        text = "Subject-Verb Agreement rule: A singular subject takes a singular verb."
        db.add(
            DocumentPage(
                document_id=doc.id,
                page_number=1,
                extracted_text=text,
                extraction_method="pymupdf",
                confidence=1.0,
                processing_status="done",
                raw_char_count=len(text),
            )
        )
        db.add(
            DocumentChunk(
                document_id=doc.id,
                chunk_index=0,
                page_start=1,
                page_end=1,
                section_title="Grammar",
                chunk_type="prose",
                content_text=text,
                token_estimate=16,
            )
        )
    db.commit()
    return doc


def test_knowledge_and_topics_endpoints_end_to_end_with_ownership(
    db_engine: Engine,
    db_session: Session,
    test_settings,
) -> None:
    owner_id = test_settings.local_default_user_id
    other_id = uuid.uuid4()
    doc_no_pages = _create_doc(db_session, user_id=owner_id, with_pages=False)
    doc = _create_doc(db_session, user_id=owner_id, with_pages=True)

    client = _make_test_client(db_engine, MockLLMProvider())

    # 1. Subjects endpoint
    subj_resp = client.get("/api/v1/subjects")
    assert subj_resp.status_code == 200
    codes = [item["subject_code"] for item in subj_resp.json()["items"]]
    assert set(codes) == {
        "quantitative_aptitude",
        "reasoning",
        "english",
        "general_awareness",
    }

    # 2. Extract knowledge returns 409 before pages/chunks exist
    conflict_resp = client.post(f"/api/v1/documents/{doc_no_pages.id}/extract-knowledge")
    assert conflict_resp.status_code == 409

    # 3. Trigger extraction on extracted document -> 202 + background run completes
    extract_resp = client.post(f"/api/v1/documents/{doc.id}/extract-knowledge")
    assert extract_resp.status_code == 202
    job_id = extract_resp.json()["id"]

    job_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    assert job_resp.json()["status"] == "completed"

    # 4. Knowledge & topics endpoints return grounded facts/concepts/topics
    knowledge_resp = client.get(f"/api/v1/documents/{doc.id}/knowledge")
    assert knowledge_resp.status_code == 200
    k_data = knowledge_resp.json()
    assert k_data["detected_subject_code"] == "english"
    assert len(k_data["facts"]) >= 1
    assert len(k_data["concepts"]) >= 1
    assert len(k_data["topics"]) >= 1
    fact_id = k_data["facts"][0]["id"]

    topics_resp = client.get(f"/api/v1/documents/{doc.id}/topics")
    assert topics_resp.status_code == 200
    assert topics_resp.json()["total"] >= 1

    global_topics_resp = client.get("/api/v1/topics?subject_code=english")
    assert global_topics_resp.status_code == 200
    assert global_topics_resp.json()["total"] >= 1

    # 5. Override classification & update fact review status
    cls_resp = client.patch(
        f"/api/v1/documents/{doc.id}/classification",
        json={"subject_code": "general_awareness", "material_type": "textbook"},
    )
    assert cls_resp.status_code == 200
    assert cls_resp.json()["subject_code"] == "general_awareness"
    assert cls_resp.json()["material_type"] == "textbook"

    patch_fact = client.patch(
        f"/api/v1/facts/{fact_id}",
        json={"review_status": "verified"},
    )
    assert patch_fact.status_code == 200
    assert patch_fact.json()["review_status"] == "verified"

    # 6. Cross-user ownership enforcement (403)
    headers_other = {"X-User-Id": str(other_id)}
    assert (
        client.get(f"/api/v1/documents/{doc.id}/knowledge", headers=headers_other).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/facts/{fact_id}",
            json={"review_status": "rejected"},
            headers=headers_other,
        ).status_code
        == 403
    )
