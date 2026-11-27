from __future__ import annotations

import hashlib
import io
import uuid
from collections.abc import Generator
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.core.config import get_settings
from app.db.session import get_db
from app.models.assessment import Question
from app.models.assessment import Test as TestModel
from app.models.assessment import TestQuestion as TestQuestionModel
from app.models.document import Document


def _make_pdf_bytes(
    page_count: int = 1,
    *,
    text: str = "SSC CHSL Maths",
    password: str | None = None,
) -> bytes:
    doc = pymupdf.open()
    try:
        for i in range(page_count):
            page = doc.new_page()
            page.insert_text((72, 72), f"{text} - Page {i + 1}")
        if password:
            return doc.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                user_pw=password,
                owner_pw=f"{password}_owner",
            )
        return doc.tobytes()
    finally:
        doc.close()


def _make_image_bytes(fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (40, 40), color=(20, 120, 200))
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_upload_valid_pdf_stores_privately_and_hides_storage_key(
    client: TestClient,
    isolated_env: tuple[Path, Path],
    db_session: Session,
) -> None:
    _, storage_dir = isolated_env
    pdf_bytes = _make_pdf_bytes(page_count=2, text="Percentages Notes")

    resp = client.post(
        "/api/v1/documents",
        files={"file": ("percentages.pdf", pdf_bytes, "application/pdf")},
        data={
            "title": "Percentages Guide",
            "subject_code": "quantitative_aptitude",
            "material_type": "notes",
            "language": "en",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Percentages Guide"
    assert body["source_type"] == "pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["page_count"] == 2
    assert body["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert "storage_key" not in body
    assert "deleted_at" not in body

    doc_row = db_session.get(Document, uuid.UUID(body["id"]))
    assert doc_row is not None
    stored_path = storage_dir / doc_row.storage_key
    assert stored_path.is_file()
    assert stored_path.read_bytes() == pdf_bytes

    # Stored file must NOT be served from a public static URL
    static_probe = client.get(f"/storage/{doc_row.storage_key}")
    assert static_probe.status_code == 404


def test_upload_valid_images_and_plain_text_ingestion(
    client: TestClient,
    isolated_env: tuple[Path, Path],
    db_session: Session,
) -> None:
    _, storage_dir = isolated_env

    png_resp = client.post(
        "/api/v1/documents",
        files={"file": ("figure.png", _make_image_bytes("PNG"), "image/png")},
        data={"material_type": "question_bank"},
    )
    assert png_resp.status_code == 201
    assert png_resp.json()["source_type"] == "image"
    assert png_resp.json()["page_count"] == 1

    jpg_resp = client.post(
        "/api/v1/documents",
        files={"file": ("scan.jpg", _make_image_bytes("JPEG"), "image/jpeg")},
    )
    assert jpg_resp.status_code == 201
    assert jpg_resp.json()["source_type"] == "image"
    assert jpg_resp.json()["mime_type"] == "image/jpeg"

    text_resp = client.post(
        "/api/v1/documents/text",
        json={
            "title": "Quick Idioms",
            "content": "A blessing in disguise: an apparent misfortune that turns out well.",
            "subject_code": "english",
            "material_type": "notes",
        },
    )
    assert text_resp.status_code == 201
    text_body = text_resp.json()
    assert text_body["source_type"] == "plain_text"
    assert text_body["mime_type"] == "text/plain"
    assert text_body["page_count"] == 1
    assert "storage_key" not in text_body

    doc_row = db_session.get(Document, uuid.UUID(text_body["id"]))
    assert doc_row is not None
    assert (storage_dir / doc_row.storage_key).is_file()

    blank_text_resp = client.post(
        "/api/v1/documents/text",
        json={"title": "   ", "content": "Valid content"},
    )
    assert blank_text_resp.status_code == 422


def test_upload_rejects_spoofed_corrupt_encrypted_oversized_and_over_page_limit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. Spoofed extension (.pdf containing plain text or EXE header)
    txt_as_pdf = client.post(
        "/api/v1/documents",
        files={"file": ("spoof.pdf", b"Just plain text pretending to be PDF", "application/pdf")},
    )
    assert txt_as_pdf.status_code == 422

    exe_as_pdf = client.post(
        "/api/v1/documents",
        files={"file": ("malware.pdf", b"MZ\x90\x00fake-pe-header", "application/pdf")},
    )
    assert exe_as_pdf.status_code == 422

    # 2. MIME mismatch
    mime_mismatch = client.post(
        "/api/v1/documents",
        files={"file": ("real.pdf", _make_pdf_bytes(), "image/png")},
    )
    assert mime_mismatch.status_code == 422

    # 3. Corrupt PDF
    corrupt_pdf = client.post(
        "/api/v1/documents",
        files={"file": ("corrupt.pdf", b"%PDF-1.4\n%%%broken-xref-stream", "application/pdf")},
    )
    assert corrupt_pdf.status_code == 422

    # 4. Encrypted / password-protected PDF
    locked_pdf = client.post(
        "/api/v1/documents",
        files={"file": ("locked.pdf", _make_pdf_bytes(password="pass123"), "application/pdf")},
    )
    assert locked_pdf.status_code == 422

    # 5. Oversized payload (413) & exceeded max page limit (422)
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("MAX_PDF_PAGES", "2")
    get_settings.cache_clear()

    oversized_bytes = b"%PDF-1.4\n" + (b"A" * (1024 * 1024 + 64))
    oversized_resp = client.post(
        "/api/v1/documents",
        files={"file": ("huge.pdf", oversized_bytes, "application/pdf")},
    )
    assert oversized_resp.status_code == 413

    many_pages_resp = client.post(
        "/api/v1/documents",
        files={"file": ("many.pdf", _make_pdf_bytes(page_count=4), "application/pdf")},
    )
    assert many_pages_resp.status_code == 422


def test_duplicate_sha256_conflict_allow_duplicate_and_cross_user_isolation(
    client: TestClient,
) -> None:
    pdf_bytes = _make_pdf_bytes(text="Duplicate Check Paper")

    first = client.post(
        "/api/v1/documents",
        files={"file": ("paper1.pdf", pdf_bytes, "application/pdf")},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    dup = client.post(
        "/api/v1/documents",
        files={"file": ("paper1_copy.pdf", pdf_bytes, "application/pdf")},
    )
    assert dup.status_code == 409
    dup_body = dup.json()
    assert dup_body["code"] == "DUPLICATE_DOCUMENT"
    assert dup_body["existing_document_id"] == first_id

    allowed = client.post(
        "/api/v1/documents",
        files={"file": ("paper1_copy.pdf", pdf_bytes, "application/pdf")},
        data={"allow_duplicate": "true"},
    )
    assert allowed.status_code == 201
    assert allowed.json()["id"] != first_id

    # Second user uploading the exact same SHA-256 succeeds independently
    user_b_headers = {"X-User-Id": "00000000-0000-0000-0000-000000000002"}
    user_b_upload = client.post(
        "/api/v1/documents",
        headers=user_b_headers,
        files={"file": ("paper1.pdf", pdf_bytes, "application/pdf")},
    )
    assert user_b_upload.status_code == 201
    assert user_b_upload.json()["user_id"] == "00000000-0000-0000-0000-000000000002"


def test_persistence_across_restart_and_ownership_enforcement(
    client: TestClient,
    db_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_bytes = _make_pdf_bytes(text="Reasoning Syllogism")
    created = client.post(
        "/api/v1/documents",
        files={"file": ("syllogism.pdf", pdf_bytes, "application/pdf")},
        data={"title": "Syllogism Notes", "subject_code": "reasoning", "material_type": "notes"},
    )
    assert created.status_code == 201
    doc_id = created.json()["id"]

    # Simulate backend restart with a brand-new FastAPI app & DB session factory over same DB
    fresh_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", fresh_session_local)
    restarted_app = main_module.create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        db = fresh_session_local()
        try:
            yield db
        finally:
            db.close()

    restarted_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(restarted_app) as fresh_client:
        listing = fresh_client.get("/api/v1/documents", params={"subject_code": "reasoning"})
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["id"] == doc_id

        detail = fresh_client.get(f"/api/v1/documents/{doc_id}")
        assert detail.status_code == 200
        assert detail.json()["title"] == "Syllogism Notes"

        patched = fresh_client.patch(
            f"/api/v1/documents/{doc_id}",
            json={"title": "Syllogism Notes Updated"},
        )
        assert patched.status_code == 200
        assert patched.json()["title"] == "Syllogism Notes Updated"

        # Cross-user ownership enforcement
        user_b_headers = {"X-User-Id": "00000000-0000-0000-0000-000000000002"}
        assert (
            fresh_client.get(f"/api/v1/documents/{doc_id}", headers=user_b_headers).status_code
            == 403
        )
        assert (
            fresh_client.patch(
                f"/api/v1/documents/{doc_id}",
                headers=user_b_headers,
                json={"title": "Hijacked"},
            ).status_code
            == 403
        )
        assert (
            fresh_client.delete(f"/api/v1/documents/{doc_id}", headers=user_b_headers).status_code
            == 403
        )
        assert fresh_client.get("/api/v1/documents", headers=user_b_headers).json()["total"] == 0

        # Missing UUID -> 404
        missing_id = str(uuid.uuid4())
        assert fresh_client.get(f"/api/v1/documents/{missing_id}").status_code == 404


def test_delete_document_removes_storage_and_preserves_test_referenced_questions(
    client: TestClient,
    isolated_env: tuple[Path, Path],
    db_session: Session,
    test_settings,
) -> None:
    _, storage_dir = isolated_env
    pdf_bytes = _make_pdf_bytes(text="Trigonometry PYQ")
    created = client.post(
        "/api/v1/documents",
        files={"file": ("trig.pdf", pdf_bytes, "application/pdf")},
    )
    assert created.status_code == 201
    doc_id = uuid.UUID(created.json()["id"])

    doc_row = db_session.get(Document, doc_id)
    assert doc_row is not None
    stored_file = storage_dir / doc_row.storage_key
    assert stored_file.is_file()

    # Seed one question referenced by a TestQuestion and one unreferenced question
    referenced_q = Question(
        document_id=doc_id,
        subject_code="quantitative_aptitude",
        question_text="What is sin(30 deg)?",
        stem_hash="hash_ref_1",
        correct_answer_data={"correct_option_key": "A"},
        explanation="sin(30) = 1/2",
        answer_key_provenance="source_answer_key",
        validation_status="verified",
    )
    unreferenced_q = Question(
        document_id=doc_id,
        subject_code="quantitative_aptitude",
        question_text="What is cos(0 deg)?",
        stem_hash="hash_unref_2",
        correct_answer_data={"correct_option_key": "B"},
        explanation="cos(0) = 1",
        answer_key_provenance="source_answer_key",
        validation_status="verified",
    )
    test_row = TestModel(
        user_id=test_settings.local_default_user_id,
        title="Trig Drill",
        total_questions=1,
    )
    db_session.add_all([referenced_q, unreferenced_q, test_row])
    db_session.flush()

    tq = TestQuestionModel(
        test_id=test_row.id,
        question_id=referenced_q.id,
        display_order=1,
        question_snapshot_json={"question_text": referenced_q.question_text},
    )
    db_session.add(tq)
    db_session.commit()

    referenced_q_id = referenced_q.id
    unreferenced_q_id = unreferenced_q.id

    del_resp = client.delete(f"/api/v1/documents/{doc_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted_id"] == str(doc_id)
    assert del_resp.json()["storage_removed"] is True
    assert not stored_file.exists()

    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404

    db_session.expire_all()
    kept_q = db_session.execute(
        select(Question).where(Question.id == referenced_q_id)
    ).scalar_one_or_none()
    dropped_q = db_session.execute(
        select(Question).where(Question.id == unreferenced_q_id)
    ).scalar_one_or_none()
    assert kept_q is not None
    assert kept_q.document_id is None
    assert dropped_q is None


def test_exam_configs_endpoint_returns_seeded_ssc_chsl(client: TestClient) -> None:
    list_resp = client.get("/api/v1/exam-configs")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] >= 1
    codes = [item["exam_code"] for item in body["items"]]
    assert "ssc_chsl_tier_1" in codes

    single_resp = client.get("/api/v1/exam-configs/ssc_chsl_tier_1")
    assert single_resp.status_code == 200
    assert single_resp.json()["name"] == "SSC CHSL Tier 1"

    assert client.get("/api/v1/exam-configs/nonexistent_exam").status_code == 404
