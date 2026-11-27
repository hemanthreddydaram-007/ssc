from __future__ import annotations

import io
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.api.v1 import jobs as jobs_module
from app.db.session import get_db
from app.models.document import Document, DocumentChunk
from app.services.extraction.extraction_pipeline import ExtractionPipeline
from app.services.extraction.ocr_adapter import OCRPageResult


@pytest.fixture
def extraction_client(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """TestClient with both documents and jobs routers mounted against isolated DB."""
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)
    app = main_module.create_app()

    # Mount jobs router if router.py hasn't wired it yet in Wave 1
    existing_paths = {route.path for route in app.routes}
    if "/api/v1/jobs" not in existing_paths:
        app.include_router(jobs_module.router, prefix="/api/v1")

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as tc:
        yield tc


def _build_text_and_diagram_pdf() -> bytes:
    doc = pymupdf.open()
    try:
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(
            (50, 120),
            "Q.1 What is 15% of 200 in SSC CHSL quantitative aptitude?\n"
            "(A) 20\n(B) 25\n(C) 30\n(D) 35",
        )
        p1.insert_text(
            (330, 120),
            "Q.2 Right column ratio question with complete options below.\n"
            "(A) 2:3\n(B) 3:4\n(C) 4:5\n(D) 5:6",
        )
        shape = p1.new_shape()
        shape.draw_rect(pymupdf.Rect(80, 320, 220, 440))
        shape.draw_circle((150, 380), 40)
        shape.finish(color=(0, 0, 0), width=1.5)
        shape.commit()

        p2 = doc.new_page(width=595, height=842)
        p2.insert_text(
            (72, 120),
            "NUMBER SYSTEM NOTES\n"
            "A prime number has exactly two positive divisors: 1 and itself.",
        )
        return doc.tobytes()
    finally:
        doc.close()


def _build_scanned_pdf() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (240, 240), color=(210, 220, 230)).save(buf, format="PNG")
    img_bytes = buf.getvalue()

    doc = pymupdf.open()
    try:
        page = doc.new_page(width=400, height=400)
        page.insert_image(pymupdf.Rect(20, 20, 380, 380), stream=img_bytes)
        return doc.tobytes()
    finally:
        doc.close()


def test_process_text_pdf_populates_pages_chunks_assets_and_coverage(
    extraction_client: TestClient,
    db_session: Session,
) -> None:
    pdf_bytes = _build_text_and_diagram_pdf()
    upload = extraction_client.post(
        "/api/v1/documents",
        files={"file": ("quant_pyq.pdf", pdf_bytes, "application/pdf")},
        data={"title": "Quant PYQ", "material_type": "pyq"},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    proc = extraction_client.post(
        f"/api/v1/documents/{doc_id}/process",
        json={"mode": "extract_only"},
    )
    assert proc.status_code == 202
    job_body = proc.json()
    job_id = job_body["id"]

    # Poll / check completed job via GET /api/v1/jobs/{job_id}
    job_status_resp = extraction_client.get(f"/api/v1/jobs/{job_id}")
    assert job_status_resp.status_code == 200
    job_data = job_status_resp.json()
    assert job_data["status"] == "completed"
    assert job_data["total_items"] == 2
    assert job_data["processed_items"] == 2
    assert job_data["progress_percent"] == 100
    stage_names = [s["name"] for s in job_data["stages"]]
    assert stage_names == [
        "page_extraction",
        "ocr_fallback",
        "semantic_chunking",
        "coverage_audit",
    ]
    stage_by_name = {s["name"]: s for s in job_data["stages"]}
    assert stage_by_name["page_extraction"]["status"] == "completed"
    assert stage_by_name["page_extraction"]["processed_items"] == 2
    assert stage_by_name["page_extraction"]["total_items"] == 2
    assert stage_by_name["ocr_fallback"]["status"] == "skipped"
    assert stage_by_name["semantic_chunking"]["status"] == "completed"
    assert stage_by_name["semantic_chunking"]["processed_items"] >= 2
    assert stage_by_name["coverage_audit"]["status"] == "completed"
    assert stage_by_name["coverage_audit"]["processed_items"] == 1

    pages_resp = extraction_client.get(f"/api/v1/documents/{doc_id}/pages")
    assert pages_resp.status_code == 200
    pages_body = pages_resp.json()
    assert pages_body["page_count"] == 2
    assert len(pages_body["items"]) == 2

    p1 = pages_body["items"][0]
    assert p1["page_number"] == 1
    assert p1["needs_ocr"] is False
    assert "Q.1 What is 15% of 200" in p1["extracted_text"]
    assert p1["extracted_text"].index("Q.1") < p1["extracted_text"].index("Q.2")
    assert len(p1["assets"]) >= 1
    assert "storage_key" not in p1["assets"][0]

    # Stream private asset & verify ownership enforcement
    asset_id = p1["assets"][0]["id"]
    asset_resp = extraction_client.get(f"/api/v1/documents/{doc_id}/assets/{asset_id}")
    assert asset_resp.status_code == 200
    assert asset_resp.headers["content-type"].startswith("image/")
    assert len(asset_resp.content) > 0

    user_b = {"X-User-Id": "00000000-0000-0000-0000-000000000002"}
    assert (
        extraction_client.get(
            f"/api/v1/documents/{doc_id}/assets/{asset_id}", headers=user_b
        ).status_code
        == 403
    )
    assert (
        extraction_client.get(
            f"/api/v1/documents/{doc_id}/assets/{uuid.uuid4()}"
        ).status_code
        == 404
    )

    # Coverage audit reflects real DB state
    cov_resp = extraction_client.get(f"/api/v1/documents/{doc_id}/coverage")
    assert cov_resp.status_code == 200
    cov = cov_resp.json()
    assert cov["total_pages"] == 2
    assert cov["pages_extracted_text"] == 2
    assert cov["pages_requiring_ocr"] == 0
    assert cov["images_extracted"] >= 1
    assert cov["chunks_created"] >= 2
    assert cov["low_confidence_topics"] == []

    # Chunks persisted in DB
    db_session.expire_all()
    chunks = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(doc_id))
    ).scalars().all()
    assert len(chunks) == cov["chunks_created"]
    doc_row = db_session.get(Document, uuid.UUID(doc_id))
    assert doc_row is not None and doc_row.status == "extracted"


def test_scanned_pdf_flags_needs_ocr_and_filters_pages_honestly(
    extraction_client: TestClient,
) -> None:
    upload = extraction_client.post(
        "/api/v1/documents",
        files={"file": ("scanned_notes.pdf", _build_scanned_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    proc = extraction_client.post(f"/api/v1/documents/{doc_id}/process", json={})
    assert proc.status_code == 202

    flagged = extraction_client.get(
        f"/api/v1/documents/{doc_id}/pages", params={"needs_ocr_only": "true"}
    )
    assert flagged.status_code == 200
    items = flagged.json()["items"]
    assert len(items) == 1
    assert items[0]["needs_ocr"] is True
    assert items[0]["processing_status"] == "needs_ocr"
    assert items[0]["extracted_text"] == ""
    assert items[0]["warning"] is not None

    cov = extraction_client.get(f"/api/v1/documents/{doc_id}/coverage").json()
    assert cov["total_pages"] == 1
    assert cov["pages_extracted_text"] == 0
    assert cov["pages_requiring_ocr"] == 1
    assert len(cov["low_confidence_pages"]) == 1
    assert cov["low_confidence_pages"][0]["page_number"] == 1


def test_jobs_list_retry_and_cross_user_isolation(
    extraction_client: TestClient,
) -> None:
    text_doc = extraction_client.post(
        "/api/v1/documents/text",
        json={
            "title": "Polity Articles",
            "content": (
                "Article 14 guarantees equality before the law.\n\n"
                "Article 21 protects life."
            ),
        },
    )
    assert text_doc.status_code == 201
    doc_id = text_doc.json()["id"]

    proc = extraction_client.post(f"/api/v1/documents/{doc_id}/process", json={})
    assert proc.status_code == 202
    first_job_id = proc.json()["id"]

    listing = extraction_client.get("/api/v1/jobs", params={"document_id": doc_id})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == first_job_id

    retry_resp = extraction_client.post(f"/api/v1/jobs/{first_job_id}/retry")
    assert retry_resp.status_code == 202
    retry_body = retry_resp.json()
    assert retry_body["id"] != first_job_id
    assert retry_body["retry_count"] == 1

    # Verify retry completed cleanly without page/chunk unique-constraint collisions
    retried_status = extraction_client.get(f"/api/v1/jobs/{retry_body['id']}").json()
    assert retried_status["status"] == "completed"

    # Cross-user isolation
    user_b = {"X-User-Id": "00000000-0000-0000-0000-000000000002"}
    assert extraction_client.get("/api/v1/jobs", headers=user_b).json()["total"] == 0
    assert (
        extraction_client.get(f"/api/v1/jobs/{first_job_id}", headers=user_b).status_code
        == 403
    )
    assert (
        extraction_client.post(
            f"/api/v1/jobs/{first_job_id}/retry", headers=user_b
        ).status_code
        == 403
    )
    assert (
        extraction_client.get(
            f"/api/v1/documents/{doc_id}/pages", headers=user_b
        ).status_code
        == 403
    )
    assert (
        extraction_client.get(
            f"/api/v1/documents/{doc_id}/coverage", headers=user_b
        ).status_code
        == 403
    )
    assert (
        extraction_client.post(
            f"/api/v1/documents/{doc_id}/process", json={}, headers=user_b
        ).status_code
        == 403
    )
    assert extraction_client.get(f"/api/v1/jobs/{uuid.uuid4()}").status_code == 404


def test_jobs_routes_are_mounted_in_default_app_router(client: TestClient) -> None:
    """Verify Wave 2 router.py wiring without manually mounting jobs_module.router."""
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


class _FakeOCRAdapter:
    """Deterministic OCR test double returning structured MCQ text."""

    provider_name = "fake_ocr"

    def extract_page(
        self,
        image_bytes: bytes,
        mime_type: str,
        page_number: int,
        language_hint: str = "en",
    ) -> OCRPageResult:
        assert len(image_bytes) > 0
        assert mime_type == "image/png"
        return OCRPageResult(
            page_number=page_number,
            extracted_text=(
                "Q.1 Recovered from scan: Which article abolishes untouchability?\n"
                "(A) Article 14\n(B) Article 17\n(C) Article 19\n(D) Article 21"
            ),
            confidence=0.92,
            ocr_provider="fake_ocr",
            warning=None,
        )


def test_fake_ocr_adapter_populates_needs_ocr_pages_and_chunks(
    extraction_client: TestClient,
    db_session: Session,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scanned PDF gets flagged under NullOCRAdapter, then populated via FakeOCRAdapter."""
    _, storage_dir = isolated_env
    upload = extraction_client.post(
        "/api/v1/documents",
        files={"file": ("scanned_polity.pdf", _build_scanned_pdf(), "application/pdf")},
        data={"title": "Scanned Polity PYQ"},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    # First pass with default NullOCRAdapter leaves needs_ocr=True
    first_proc = extraction_client.post(f"/api/v1/documents/{doc_id}/process", json={})
    assert first_proc.status_code == 202
    first_job = extraction_client.get(f"/api/v1/jobs/{first_proc.json()['id']}").json()
    ocr_stage_first = next(s for s in first_job["stages"] if s["name"] == "ocr_fallback")
    assert ocr_stage_first["status"] == "skipped"
    assert ocr_stage_first["processed_items"] == 0
    assert ocr_stage_first["total_items"] == 1

    # Second pass ("ocr_retry") with FakeOCRAdapter injected
    monkeypatch.setattr(
        "app.services.extraction.extraction_pipeline.ExtractionPipeline.__init__",
        lambda self, storage_root, ocr_adapter=None: (
            setattr(self, "storage_root", storage_root)
            or setattr(self, "ocr_adapter", ocr_adapter or _FakeOCRAdapter())
        ),
    )

    retry_proc = extraction_client.post(
        f"/api/v1/documents/{doc_id}/process",
        json={"mode": "ocr_retry"},
    )
    assert retry_proc.status_code == 202
    retry_job = extraction_client.get(f"/api/v1/jobs/{retry_proc.json()['id']}").json()
    assert retry_job["status"] == "completed"
    ocr_stage_retry = next(s for s in retry_job["stages"] if s["name"] == "ocr_fallback")
    assert ocr_stage_retry["status"] == "completed"
    assert ocr_stage_retry["processed_items"] == 1
    assert ocr_stage_retry["total_items"] == 1

    pages = extraction_client.get(f"/api/v1/documents/{doc_id}/pages").json()["items"]
    assert len(pages) == 1
    p1 = pages[0]
    assert p1["needs_ocr"] is False
    assert p1["ocr_provider"] == "fake_ocr"
    assert p1["extraction_method"] == "ocr_fake_ocr"
    assert p1["processing_status"] == "done"
    assert "Article 17" in p1["extracted_text"]

    cov = extraction_client.get(f"/api/v1/documents/{doc_id}/coverage").json()
    assert cov["pages_extracted_ocr"] == 1
    assert cov["pages_requiring_ocr"] == 0
    assert cov["chunks_created"] >= 1

    db_session.expire_all()
    chunks = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(doc_id))
    ).scalars().all()
    assert any("Article 17" in c.content_text for c in chunks)
    assert storage_dir.exists()


def _build_table_pdf() -> bytes:
    """Create a 1-page PDF with an explicit bordered grid table for pdfplumber."""
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 80), "IMPORTANT CONSTITUTIONAL AMENDMENTS")
        # Draw a 3x2 grid table with explicit lines so pdfplumber detects cells reliably
        x_cols = [60, 220, 420]
        y_rows = [120, 155, 190, 225]
        shape = page.new_shape()
        for y in y_rows:
            shape.draw_line((x_cols[0], y), (x_cols[-1], y))
        for x in x_cols:
            shape.draw_line((x, y_rows[0]), (x, y_rows[-1]))
        shape.finish(color=(0, 0, 0), width=1.0)
        shape.commit()

        page.insert_text((70, 142), "Amendment")
        page.insert_text((230, 142), "Key Change")
        page.insert_text((70, 177), "42nd")
        page.insert_text((230, 177), "Fundamental Duties")
        page.insert_text((70, 212), "44th")
        page.insert_text((230, 212), "Right to Property")
        return doc.tobytes()
    finally:
        doc.close()


def test_pdf_with_table_extracts_tables_json_and_table_chunks(
    extraction_client: TestClient,
    db_session: Session,
) -> None:
    upload = extraction_client.post(
        "/api/v1/documents",
        files={"file": ("amendments_table.pdf", _build_table_pdf(), "application/pdf")},
        data={"title": "Amendments Table"},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    proc = extraction_client.post(f"/api/v1/documents/{doc_id}/process", json={})
    assert proc.status_code == 202

    pages = extraction_client.get(f"/api/v1/documents/{doc_id}/pages").json()["items"]
    assert len(pages) == 1
    p1 = pages[0]
    assert p1["table_count"] >= 1
    assert p1["tables_json"] is not None
    flattened = " ".join(str(cell) for tbl in p1["tables_json"] for row in tbl for cell in row)
    assert "42nd" in flattened
    assert "Fundamental Duties" in flattened

    cov = extraction_client.get(f"/api/v1/documents/{doc_id}/coverage").json()
    assert cov["tables_extracted"] >= 1

    db_session.expire_all()
    chunks = db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(doc_id))
    ).scalars().all()
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) >= 1
    assert "Fundamental Duties" in table_chunks[0].content_text


def test_get_pages_coverage_assets_and_jobs_make_zero_llm_calls(
    extraction_client: TestClient,
) -> None:
    upload = extraction_client.post(
        "/api/v1/documents",
        files={"file": ("notes.pdf", _build_text_and_diagram_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    proc = extraction_client.post(f"/api/v1/documents/{doc_id}/process", json={})
    assert proc.status_code == 202
    job_id = proc.json()["id"]

    with (
        patch(
            "httpx.HTTPTransport.handle_request",
            side_effect=AssertionError("Unexpected outbound HTTP/LLM call"),
        ),
        patch(
            "httpx.AsyncHTTPTransport.handle_async_request",
            side_effect=AssertionError("Unexpected async HTTP/LLM call"),
        ),
        patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("Unexpected urllib HTTP/LLM call"),
        ),
    ):
        pages_resp = extraction_client.get(f"/api/v1/documents/{doc_id}/pages")
        assert pages_resp.status_code == 200
        cov_resp = extraction_client.get(f"/api/v1/documents/{doc_id}/coverage")
        assert cov_resp.status_code == 200
        job_resp = extraction_client.get(f"/api/v1/jobs/{job_id}")
        assert job_resp.status_code == 200
        asset_id = pages_resp.json()["items"][0]["assets"][0]["id"]
        asset_resp = extraction_client.get(f"/api/v1/documents/{doc_id}/assets/{asset_id}")
        assert asset_resp.status_code == 200


def test_honest_progress_percent_when_total_items_zero(
    extraction_client: TestClient,
) -> None:
    """Initial queued job and 0-matching-page job report progress_percent=None, never fake 100."""
    upload = extraction_client.post(
        "/api/v1/documents",
        files={"file": ("two_pages.pdf", _build_text_and_diagram_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    # Queued response returned immediately before background task finishes has total_items=0 -> None
    proc = extraction_client.post(
        f"/api/v1/documents/{doc_id}/process",
        json={"mode": "extract_only", "page_numbers": [999]},
    )
    assert proc.status_code == 202
    initial_job = proc.json()
    assert initial_job["total_items"] == 0
    assert initial_job["progress_percent"] is None

    # After completion with 0 matching pages, progress_percent remains None (not fake 100)
    finished_job = extraction_client.get(f"/api/v1/jobs/{initial_job['id']}").json()
    assert finished_job["status"] == "completed"
    assert finished_job["total_items"] == 0
    assert finished_job["progress_percent"] is None


def test_delete_document_removes_extracted_assets_from_storage(
    extraction_client: TestClient,
    isolated_env: tuple[Path, Path],
) -> None:
    _, storage_dir = isolated_env
    upload = extraction_client.post(
        "/api/v1/documents",
        files={"file": ("with_diagram.pdf", _build_text_and_diagram_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201
    doc_id = upload.json()["id"]

    proc = extraction_client.post(f"/api/v1/documents/{doc_id}/process", json={})
    assert proc.status_code == 202

    pages = extraction_client.get(f"/api/v1/documents/{doc_id}/pages").json()["items"]
    asset_id = pages[0]["assets"][0]["id"]
    asset_files_before = list(storage_dir.rglob(f"*{asset_id}*"))
    assert len(asset_files_before) == 1

    del_resp = extraction_client.delete(f"/api/v1/documents/{doc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["storage_removed"] is True

    asset_files_after = list(storage_dir.rglob(f"*{asset_id}*"))
    assert asset_files_after == []
    assert extraction_client.get(f"/api/v1/documents/{doc_id}/pages").status_code == 404
    assert (
        extraction_client.get(f"/api/v1/documents/{doc_id}/assets/{asset_id}").status_code == 404
    )
    # Keep import used for static type/lint verification
    assert ExtractionPipeline is not None
