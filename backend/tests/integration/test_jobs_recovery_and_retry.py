from __future__ import annotations

import io
import uuid
from collections.abc import Generator
from datetime import timedelta

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.jobs as jobs_module
import app.main as main_module
from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.core.config import Settings
from app.db.base import utcnow
from app.db.session import get_db
from app.models.document import Document, DocumentChunk, DocumentPage, ProcessingJob
from app.models.learning import Note
from app.models.user import User
from app.repositories.job_repo import (
    INTERRUPTED_ERROR_CODE,
    register_active_job,
    unregister_active_job,
)


def _make_pdf_bytes(text: str = "SSC Quant Percentage Notes") -> bytes:
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        page.insert_text((50, 72), text)
        return doc.tobytes()
    finally:
        doc.close()


def _seed_doc_with_pages_and_chunks(
    db: Session,
    *,
    user_id: uuid.UUID,
    title: str = "Quant Speed Tricks",
) -> Document:
    if db.get(User, user_id) is None:
        db.add(User(id=user_id, display_name="Test Student"))
        db.flush()

    doc = Document(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        original_filename="quant.pdf",
        source_type="pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_key=f"users/{user_id}/quant.pdf",
        subject_code="quantitative_aptitude",
        material_type="notes",
        language="en",
        page_count=1,
        status="extracted",
    )
    db.add(doc)
    db.flush()

    text = "Percentage formula: Successive change of x% and y% equals x + y + (x*y)/100 percent."
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
            section_title="Percentages",
            chunk_type="prose",
            content_text=text,
            token_estimate=20,
        )
    )
    db.commit()
    return doc


def test_startup_lifespan_recovers_orphaned_jobs_as_retryable(
    db_engine: Engine,
    isolated_env: tuple[object, object],
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FastAPI startup lifespan must mark orphaned queued/running jobs as JOB_INTERRUPTED."""
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)

    with testing_session_local() as db:
        doc = _seed_doc_with_pages_and_chunks(
            db,
            user_id=test_settings.local_default_user_id,
            title="SSC Polity Notes",
        )
        running_job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=doc.id,
            triggered_by_user_id=test_settings.local_default_user_id,
            job_type="extract_only",
            status="running",
            current_stage="semantic_chunking",
            stage_details_json=[
                {"name": "page_extraction", "status": "completed", "retryable": False},
                {"name": "semantic_chunking", "status": "running", "retryable": False},
                {"name": "coverage_audit", "status": "pending", "retryable": False},
            ],
            processed_items=1,
            total_items=3,
            progress_percent=33,
            started_at=utcnow(),
        )
        queued_job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=doc.id,
            triggered_by_user_id=test_settings.local_default_user_id,
            job_type="extract_knowledge",
            status="queued",
            current_stage="queued",
            stage_details_json=[
                {"name": "classify_document", "status": "pending", "retryable": False},
            ],
            processed_items=0,
            total_items=1,
            progress_percent=0,
        )
        db.add_all([running_job, queued_job])
        db.commit()
        running_id = running_job.id
        queued_id = queued_job.id

    app = main_module.create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as tc:
        list_resp = tc.get("/api/v1/jobs")
        assert list_resp.status_code == 200
        by_id = {item["id"]: item for item in list_resp.json()["items"]}
        assert by_id[str(running_id)]["document_title"] == "SSC Polity Notes"
        assert by_id[str(queued_id)]["document_title"] == "SSC Polity Notes"

        r_job = tc.get(f"/api/v1/jobs/{running_id}").json()
        assert r_job["status"] == "failed"
        assert r_job["error_code"] == INTERRUPTED_ERROR_CODE
        assert "Retry" in r_job["error_message"]
        assert r_job["finished_at"] is not None
        assert r_job["document_title"] == "SSC Polity Notes"
        chunk_stage = next(s for s in r_job["stages"] if s["name"] == "semantic_chunking")
        assert chunk_stage["status"] == "failed"
        assert chunk_stage["error_code"] == INTERRUPTED_ERROR_CODE
        assert chunk_stage["retryable"] is True

        q_job = tc.get(f"/api/v1/jobs/{queued_id}").json()
        assert q_job["status"] == "failed"
        assert q_job["error_code"] == INTERRUPTED_ERROR_CODE
        assert q_job["stages"][0]["status"] == "failed"
        assert q_job["stages"][0]["retryable"] is True


def test_runtime_stale_recovery_respects_heartbeats_and_populates_dashboard_title(
    client: TestClient,
    db_session: Session,
    test_settings: Settings,
) -> None:
    """Stale >10m jobs without heartbeats recover while active heartbeats stay running."""
    doc = _seed_doc_with_pages_and_chunks(
        db_session,
        user_id=test_settings.local_default_user_id,
        title="SSC Geography Atlas",
    )
    old_time = utcnow() - timedelta(minutes=11)
    stale_job = ProcessingJob(
        id=uuid.uuid4(),
        document_id=doc.id,
        triggered_by_user_id=test_settings.local_default_user_id,
        job_type="extract_only",
        status="running",
        current_stage="ocr_fallback",
        stage_details_json=[{"name": "ocr_fallback", "status": "running", "retryable": False}],
        started_at=old_time,
        created_at=old_time,
    )
    live_job = ProcessingJob(
        id=uuid.uuid4(),
        document_id=doc.id,
        triggered_by_user_id=test_settings.local_default_user_id,
        job_type="generate_notes",
        status="running",
        current_stage="generate_notes",
        stage_details_json=[{"name": "generate_notes", "status": "running", "retryable": False}],
        started_at=old_time,
        created_at=old_time,
    )
    db_session.add_all([stale_job, live_job])
    db_session.commit()

    register_active_job(live_job.id)
    try:
        dash_resp = client.get("/api/v1/dashboard")
        assert dash_resp.status_code == 200
        active_jobs = dash_resp.json()["active_jobs"]
        active_ids = [j["id"] for j in active_jobs]
        assert str(live_job.id) in active_ids
        assert str(stale_job.id) not in active_ids
        assert active_jobs[0]["document_title"] == "SSC Geography Atlas"

        stale_out = client.get(f"/api/v1/jobs/{stale_job.id}").json()
        assert stale_out["status"] == "failed"
        assert stale_out["error_code"] == INTERRUPTED_ERROR_CODE
        assert stale_out["document_title"] == "SSC Geography Atlas"

        live_out = client.get(f"/api/v1/jobs/{live_job.id}").json()
        assert live_out["status"] == "running"
        assert live_out["error_code"] is None
    finally:
        unregister_active_job(live_job.id)


def test_retry_extract_knowledge_generate_notes_and_document_titles(
    client: TestClient,
    db_session: Session,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry endpoint supports extract_knowledge & generate_notes and sets document_title."""
    mock_provider = MockLLMProvider()
    client.app.dependency_overrides[get_llm_provider] = lambda: mock_provider
    monkeypatch.setattr(jobs_module, "get_llm_provider", lambda _settings: mock_provider)

    try:
        # 1. Upload & process extraction job -> verify document_title on /process
        upload = client.post(
            "/api/v1/documents",
            files={"file": ("quant.pdf", io.BytesIO(_make_pdf_bytes()), "application/pdf")},
            data={"title": "Quant Speed Tricks", "material_type": "notes"},
        )
        assert upload.status_code == 201
        uploaded_doc_id = upload.json()["id"]

        proc_resp = client.post(
            f"/api/v1/documents/{uploaded_doc_id}/process",
            json={"mode": "extract_only"},
        )
        assert proc_resp.status_code == 202
        assert proc_resp.json()["document_title"] == "Quant Speed Tricks"
        assert client.get(f"/api/v1/jobs/{proc_resp.json()['id']}").json()["document_title"] == (
            "Quant Speed Tricks"
        )

        # 2. extract_knowledge create -> complete -> retry
        doc = _seed_doc_with_pages_and_chunks(
            db_session,
            user_id=test_settings.local_default_user_id,
            title="Algebra Core Pack",
        )
        k_resp = client.post(f"/api/v1/documents/{doc.id}/extract-knowledge")
        assert k_resp.status_code == 202
        k_body = k_resp.json()
        assert k_body["document_title"] == "Algebra Core Pack"
        assert client.get(f"/api/v1/jobs/{k_body['id']}").json()["status"] == "completed"

        k_retry = client.post(f"/api/v1/jobs/{k_body['id']}/retry")
        assert k_retry.status_code == 202
        kr_body = k_retry.json()
        assert kr_body["job_type"] == "extract_knowledge"
        assert kr_body["retry_count"] == 1
        assert kr_body["document_title"] == "Algebra Core Pack"
        assert client.get(f"/api/v1/jobs/{kr_body['id']}").json()["status"] == "completed"

        # 3. generate_notes parameterized job -> complete -> retry preserves note_types
        n_resp = client.post(
            f"/api/v1/documents/{doc.id}/generate-notes",
            json={"note_types": ["quick_revision", "formula_sheet"], "force_regenerate": True},
        )
        assert n_resp.status_code == 202
        n_body = n_resp.json()
        assert n_body["document_title"] == "Algebra Core Pack"
        assert client.get(f"/api/v1/jobs/{n_body['id']}").json()["status"] == "completed"

        # Remove existing notes before retry so we verify retry regenerates exactly the saved types
        for row in db_session.execute(select(Note).where(Note.document_id == doc.id)).scalars():
            db_session.delete(row)
        db_session.commit()

        n_retry = client.post(f"/api/v1/jobs/{n_body['id']}/retry")
        assert n_retry.status_code == 202
        nr_body = n_retry.json()
        assert nr_body["job_type"] == "generate_notes"
        assert nr_body["retry_count"] == 1
        assert nr_body["document_title"] == "Algebra Core Pack"
        assert client.get(f"/api/v1/jobs/{nr_body['id']}").json()["status"] == "completed"

        regenerated_notes = client.get(f"/api/v1/documents/{doc.id}/notes").json()["items"]
        assert {note["note_type"] for note in regenerated_notes} == {
            "quick_revision",
            "formula_sheet",
        }

        # 4. Legacy failed generate_notes job without _params falls back to default note types
        legacy_job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=doc.id,
            triggered_by_user_id=test_settings.local_default_user_id,
            job_type="generate_notes",
            status="failed",
            current_stage="generate_notes",
            stage_details_json=[
                {
                    "name": "generate_notes",
                    "status": "failed",
                    "error_code": INTERRUPTED_ERROR_CODE,
                    "retryable": True,
                }
            ],
            error_code=INTERRUPTED_ERROR_CODE,
        )
        db_session.add(legacy_job)
        db_session.commit()

        legacy_retry = client.post(f"/api/v1/jobs/{legacy_job.id}/retry")
        assert legacy_retry.status_code == 202
        lr_body = legacy_retry.json()
        assert lr_body["job_type"] == "generate_notes"
        assert lr_body["retry_count"] == 1
        assert lr_body["document_title"] == "Algebra Core Pack"
        assert client.get(f"/api/v1/jobs/{lr_body['id']}").json()["status"] == "completed"

        # 5. Cross-user 403 on retry
        other_headers = {"X-User-Id": str(uuid.uuid4())}
        forbidden = client.post(
            f"/api/v1/jobs/{n_body['id']}/retry",
            headers=other_headers,
        )
        assert forbidden.status_code == 403
    finally:
        client.app.dependency_overrides.pop(get_llm_provider, None)


def test_retry_failed_extract_knowledge_resumes_from_completed_chunks(
    client: TestClient,
    db_session: Session,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrying a partially-failed extract_knowledge job skips completed chunks & reuses class."""
    import json  # noqa: PLC0415

    from app.ai.provider import AIProviderError  # noqa: PLC0415

    if db_session.get(User, test_settings.local_default_user_id) is None:
        db_session.add(User(id=test_settings.local_default_user_id, display_name="Student"))
        db_session.flush()

    doc = Document(
        id=uuid.uuid4(),
        user_id=test_settings.local_default_user_id,
        title="Resumable PYQ Pack",
        original_filename="resume.pdf",
        source_type="pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_key=f"users/{test_settings.local_default_user_id}/resume.pdf",
        material_type="pyq",
        language="en",
        page_count=2,
        status="extracted",
    )
    db_session.add(doc)
    db_session.flush()

    p1_text = "Article 14 guarantees equality before law."
    p2_text = "Q.1 What is 10% of 50? (A) 4 (B) 5 (C) 6 (D) 8 Answer: B"
    db_session.add_all(
        [
            DocumentPage(
                document_id=doc.id,
                page_number=1,
                extracted_text=p1_text,
                extraction_method="pymupdf",
                confidence=1.0,
                processing_status="done",
                raw_char_count=len(p1_text),
            ),
            DocumentPage(
                document_id=doc.id,
                page_number=2,
                extracted_text=p2_text,
                extraction_method="pymupdf",
                confidence=1.0,
                processing_status="done",
                raw_char_count=len(p2_text),
            ),
            DocumentChunk(
                document_id=doc.id,
                chunk_index=0,
                page_start=1,
                page_end=1,
                section_title="Polity",
                chunk_type="prose",
                content_text=p1_text,
                token_estimate=10,
            ),
            DocumentChunk(
                document_id=doc.id,
                chunk_index=1,
                page_start=2,
                page_end=2,
                section_title="Quant",
                chunk_type="question_block",
                content_text=p2_text,
                token_estimate=15,
            ),
        ]
    )
    db_session.commit()

    mock_provider = MockLLMProvider()
    chunk_calls = 0

    def _classify_handler(_prompt: str) -> str:
        return json.dumps(
            {
                "subject_code": "general_awareness",
                "material_type": "pyq_paper",
                "language": "en",
                "confidence": 0.95,
                "topic_candidates": ["Indian Polity"],
                "rationale": "ok",
            }
        )

    def _chunk_handler(_prompt: str) -> str:
        nonlocal chunk_calls
        chunk_calls += 1
        if chunk_calls == 1:
            return json.dumps(
                {
                    "detected_subject_code": "general_awareness",
                    "facts": [
                        {
                            "fact_type": "rule",
                            "content": "Article 14 guarantees equality before law.",
                            "topic_name": "Indian Polity",
                            "source_page_number": 1,
                            "supporting_excerpt": "Article 14 guarantees equality before law.",
                            "provenance": "extracted",
                            "confidence": 0.95,
                        }
                    ],
                    "concepts": [],
                    "questions": [],
                }
            )
        if chunk_calls == 2:
            raise AIProviderError("Gemini API error (503) on knowledge_extraction:v1: overloaded")
        return json.dumps(
            {
                "detected_subject_code": "quantitative_aptitude",
                "facts": [],
                "concepts": [],
                "questions": [
                    {
                        "question_text": "What is 10% of 50?",
                        "question_type": "single_choice",
                        "subject_code": "quantitative_aptitude",
                        "topic_name": "Percentages",
                        "difficulty": "easy",
                        "options": [
                            {"key": "A", "text": "4"},
                            {"key": "B", "text": "5"},
                            {"key": "C", "text": "6"},
                            {"key": "D", "text": "8"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "10% of 50 = 5.",
                        "source_page_number": 2,
                        "supporting_excerpt": "What is 10% of 50?",
                        "answer_key_provenance": "source_answer_key",
                    }
                ],
            }
        )

    mock_provider.register_handler("document_classification", _classify_handler)
    mock_provider.register_handler("knowledge_extraction", _chunk_handler)
    mock_provider.register_handler("knowledge_extraction", _chunk_handler)
    mock_provider.register_handler("knowledge_extraction", _chunk_handler)
    client.app.dependency_overrides[get_llm_provider] = lambda: mock_provider
    monkeypatch.setattr(jobs_module, "get_llm_provider", lambda _settings: mock_provider)

    try:
        first_resp = client.post(f"/api/v1/documents/{doc.id}/extract-knowledge")
        assert first_resp.status_code == 202
        first_job = client.get(f"/api/v1/jobs/{first_resp.json()['id']}").json()
        assert first_job["status"] == "failed"
        assert first_job["processed_items"] == 1
        assert first_job["total_items"] == 2

        calls_before_retry = len(mock_provider.calls)
        retry_resp = client.post(f"/api/v1/jobs/{first_job['id']}/retry")
        assert retry_resp.status_code == 202
        retried_job = client.get(f"/api/v1/jobs/{retry_resp.json()['id']}").json()
        assert retried_job["status"] == "completed"
        assert retried_job["processed_items"] == 2
        assert retried_job["total_items"] == 2

        # Retry skipped both classification and chunk 1 — only chunk 2 called!
        new_calls = mock_provider.calls[calls_before_retry:]
        assert len(new_calls) == 1
        assert new_calls[0]["prompt_name"] == "knowledge_extraction"

        knowledge = client.get(f"/api/v1/documents/{doc.id}/knowledge").json()
        assert len(knowledge["facts"]) == 1
        questions = client.get(f"/api/v1/documents/{doc.id}/questions").json()["items"]
        assert len(questions) == 1
        assert questions[0]["question_text"] == "What is 10% of 50?"
    finally:
        client.app.dependency_overrides.pop(get_llm_provider, None)
