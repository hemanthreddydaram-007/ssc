"""M8 Security & Privacy Audit Tests.

Verifies:
  1. Zero occurrences of GEMINI_API_KEY or secret credentials in frontend/ source.
  2. storage_key and filesystem paths never leak in public API JSON responses.
  3. Private storage directory is never statically served via HTTP (/storage/... -> 404).
  4. Active-test endpoints never leak answer keys or pre-lock explanations.
  5. LocalPrivateStorage rejects path traversal, absolute paths, and null bytes.
  6. Cross-user 403 isolation across every user-owned resource family.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.db.session import get_db
from app.services.document_ingestion.storage import LocalPrivateStorage

USER_A = "00000000-0000-0000-0000-000000000001"
USER_B = "00000000-0000-0000-0000-000000000002"
AUTH_A = {"X-User-Id": USER_A}
AUTH_B = {"X-User-Id": USER_B}

FORBIDDEN_ACTIVE_KEYS = {
    "correct_option_key",
    "correct_answer_data",
    "is_correct",
    "answer_key",
    "explanation",
}


def _build_diagram_mcq_pdf() -> bytes:
    doc = pymupdf.open()
    try:
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(
            (50, 100),
            "PERCENTAGES NOTES\n"
            "Profit Percentage = (Profit / Cost Price) * 100.\n"
            "Q.1 If CP is 200 and SP is 250, find profit %?\n"
            "(A) 20% (B) 25% (C) 30% (D) 15% Answer: B",
        )
        shape = p1.new_shape()
        shape.draw_rect(pymupdf.Rect(80, 300, 220, 420))
        shape.draw_line((80, 420), (220, 300))
        shape.finish(color=(0, 0, 0), width=1.5)
        shape.commit()
        return doc.tobytes()
    finally:
        doc.close()


def _assert_no_key_or_path_leak(payload: Any, *, forbidden_substrings: tuple[str, ...]) -> None:
    """Recursively verify `storage_key` and filesystem paths never appear in JSON payloads."""
    if isinstance(payload, list):
        for item in payload:
            _assert_no_key_or_path_leak(item, forbidden_substrings=forbidden_substrings)
    elif isinstance(payload, dict):
        for key, value in payload.items():
            assert key != "storage_key", f"Payload leaked internal key 'storage_key': {payload}"
            _assert_no_key_or_path_leak(value, forbidden_substrings=forbidden_substrings)
    elif isinstance(payload, str):
        lowered = payload.lower()
        for sub in forbidden_substrings:
            assert sub.lower() not in lowered, (
                f"Payload leaked internal path/storage fragment {sub!r} inside {payload!r}"
            )


def _assert_no_answer_key_leak(payload: Any) -> None:
    if isinstance(payload, list):
        for item in payload:
            _assert_no_answer_key_leak(item)
    elif isinstance(payload, dict):
        for key, value in payload.items():
            assert key not in FORBIDDEN_ACTIVE_KEYS, (
                f"Active-test payload leaked forbidden key {key!r}: {payload}"
            )
            _assert_no_answer_key_leak(value)


@pytest.fixture
def sec_env(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Path, MockLLMProvider], None, None]:
    _, storage_dir = isolated_env
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)
    app = main_module.create_app()
    mock_provider = MockLLMProvider()

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider

    with (
        patch(
            "httpx.HTTPTransport.handle_request",
            side_effect=AssertionError("Outbound HTTP call forbidden during security audit!"),
        ),
        TestClient(app) as tc,
    ):
        yield tc, storage_dir, mock_provider


# ---------------------------------------------------------------------------
# 1. Frontend source secret scan
# ---------------------------------------------------------------------------


def test_frontend_source_contains_no_gemini_api_keys_or_secrets() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    frontend_dir = repo_root / "frontend"
    assert frontend_dir.is_dir(), f"Expected frontend dir at {frontend_dir}"

    secret_patterns = [
        re.compile(r"GEMINI_API_KEY", re.IGNORECASE),
        re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
        re.compile(r"GOOGLE_API_KEY", re.IGNORECASE),
    ]
    scanned = 0
    for ext in ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.json"):
        for path in frontend_dir.rglob(ext):
            if any(part in ("node_modules", ".next") for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            scanned += 1
            for pat in secret_patterns:
                assert not pat.search(text), (
                    f"Secret pattern {pat.pattern!r} found in frontend file {path}"
                )
    assert scanned > 0


# ---------------------------------------------------------------------------
# 5. Path traversal guards on LocalPrivateStorage
# ---------------------------------------------------------------------------


def test_local_private_storage_rejects_traversal_and_absolute_paths(tmp_path: Path) -> None:
    storage = LocalPrivateStorage(tmp_path / "private_store")
    escape_keys = [
        "../outside.pdf",
        "users/a/../../outside.pdf",
        "..\\windows_escape.pdf",
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
        "users/bad\x00key.pdf",
        "",
    ]
    for key in escape_keys:
        with pytest.raises(ValueError):
            storage.save_bytes(key, b"malicious")
        with pytest.raises(ValueError):
            storage.exists(key)
        with pytest.raises(ValueError):
            storage.open_read(key)

    # Leading-slash POSIX path is stripped inside storage root (never escapes to /etc/passwd)
    resolved_posix = storage._resolve_key("/etc/passwd")
    assert resolved_posix.is_relative_to(storage.root)


# ---------------------------------------------------------------------------
# 2, 3, 4, 6. Storage secrecy, static mount block, answer-key sealing, & 403s
# ---------------------------------------------------------------------------


def test_full_surface_no_storage_leaks_no_static_mount_no_answer_leaks_and_403s(
    sec_env: tuple[TestClient, Path, MockLLMProvider],
) -> None:
    client, storage_dir, mock_provider = sec_env

    # Upload -> Process -> Extract Knowledge -> Generate Notes -> Build & Start Test
    up = client.post(
        "/api/v1/documents",
        files={"file": ("audit_study.pdf", _build_diagram_mcq_pdf(), "application/pdf")},
        data={"title": "Security Audit Doc", "subject_code": "quantitative_aptitude"},
        headers=AUTH_A,
    )
    assert up.status_code == 201
    doc_id = up.json()["id"]

    proc = client.post(f"/api/v1/documents/{doc_id}/process", json={}, headers=AUTH_A)
    assert proc.status_code == 202
    proc_job_id = proc.json()["id"]

    mock_provider.enqueue_raw(
        json.dumps(
            {
                "detected_subject_code": "quantitative_aptitude",
                "facts": [
                    {
                        "fact_type": "formula",
                        "content": "Profit Percentage = (Profit / Cost Price) * 100.",
                        "topic_name": "Percentages",
                        "source_page_number": 1,
                        "supporting_excerpt": "Profit Percentage = (Profit / Cost Price) * 100.",
                        "provenance": "extracted",
                        "confidence": 0.95,
                    }
                ],
                "concepts": [],
                "questions": [
                    {
                        "question_text": "If CP is 200 and SP is 250, find profit percentage?",
                        "question_type": "single_choice",
                        "subject_code": "quantitative_aptitude",
                        "topic_name": "Percentages",
                        "difficulty": "easy",
                        "options": [
                            {"key": "A", "text": "20%"},
                            {"key": "B", "text": "25%"},
                            {"key": "C", "text": "30%"},
                            {"key": "D", "text": "15%"},
                        ],
                        "correct_option_key": "B",
                        "explanation": "Profit = 50, so (50 / 200) * 100 = 25.",
                        "source_page_number": 1,
                        "supporting_excerpt": "If CP is 200 and SP is 250",
                        "answer_key_provenance": "source_answer_key",
                    }
                ],
            }
        ),
        prompt_name="knowledge_extraction",
    )
    ek = client.post(f"/api/v1/documents/{doc_id}/extract-knowledge", headers=AUTH_A)
    assert ek.status_code == 202

    gn = client.post(
        f"/api/v1/documents/{doc_id}/generate-notes",
        json={"note_types": ["detailed"]},
        headers=AUTH_A,
    )
    assert gn.status_code == 202

    pages_payload = client.get(f"/api/v1/documents/{doc_id}/pages", headers=AUTH_A).json()
    asset_id = pages_payload["items"][0]["assets"][0]["id"]
    knowledge_payload = client.get(f"/api/v1/documents/{doc_id}/knowledge", headers=AUTH_A).json()
    fact_id = knowledge_payload["facts"][0]["id"]
    notes_payload = client.get(f"/api/v1/documents/{doc_id}/notes", headers=AUTH_A).json()
    note_id = notes_payload["items"][0]["id"]
    note_detail_payload = client.get(f"/api/v1/notes/{note_id}", headers=AUTH_A).json()
    questions_payload = client.get("/api/v1/questions", headers=AUTH_A).json()
    question_id = questions_payload["items"][0]["id"]

    # 3. Verify private storage directory is NEVER served statically
    stored_files = [p for p in storage_dir.rglob("*") if p.is_file()]
    assert len(stored_files) >= 1
    rel_key = stored_files[0].relative_to(storage_dir).as_posix()
    assert client.get(f"/storage/{rel_key}").status_code == 404
    assert client.get(f"/static/{rel_key}").status_code == 404
    assert client.get(f"/api/v1/storage/{rel_key}").status_code == 404

    # Build & start timed test
    test_payload = client.post(
        "/api/v1/tests",
        json={
            "title": "Audit Speed Test",
            "question_ids": [question_id],
            "question_count": 1,
            "timer_mode": "speed_challenge",
        },
        headers=AUTH_A,
    ).json()
    test_id = test_payload["id"]
    start_payload = client.post(f"/api/v1/tests/{test_id}/start", headers=AUTH_A).json()
    attempt_id = start_payload["attempt_id"]
    current_payload = client.get(f"/api/v1/attempts/{attempt_id}/current", headers=AUTH_A).json()
    dashboard_payload = client.get("/api/v1/dashboard", headers=AUTH_A).json()

    # 2. Assert storage_key and filesystem paths never appear in ANY public endpoint payload
    forbidden_paths = (str(storage_dir), storage_dir.as_posix(), f"users/{USER_A}/documents")
    for payload in (
        client.get("/api/v1/documents", headers=AUTH_A).json(),
        client.get(f"/api/v1/documents/{doc_id}", headers=AUTH_A).json(),
        pages_payload,
        notes_payload,
        note_detail_payload,
        questions_payload,
        client.get(f"/api/v1/questions/{question_id}", headers=AUTH_A).json(),
        test_payload,
        start_payload,
        current_payload,
        dashboard_payload,
    ):
        _assert_no_key_or_path_leak(payload, forbidden_substrings=forbidden_paths)

    # 4. Assert zero answer-key leaks during active test
    _assert_no_answer_key_leak(test_payload)
    _assert_no_answer_key_leak(start_payload)
    _assert_no_answer_key_leak(current_payload)

    # 6. Cross-user 403 enforcement across every user-owned endpoint
    cross_user_checks = [
        ("GET", f"/api/v1/documents/{doc_id}", None),
        ("PATCH", f"/api/v1/documents/{doc_id}", {"title": "Hijacked"}),
        ("DELETE", f"/api/v1/documents/{doc_id}", None),
        ("POST", f"/api/v1/documents/{doc_id}/process", {}),
        ("GET", f"/api/v1/documents/{doc_id}/pages", None),
        ("GET", f"/api/v1/documents/{doc_id}/assets/{asset_id}", None),
        ("GET", f"/api/v1/documents/{doc_id}/coverage", None),
        ("GET", f"/api/v1/jobs/{proc_job_id}", None),
        ("POST", f"/api/v1/jobs/{proc_job_id}/retry", None),
        ("POST", f"/api/v1/documents/{doc_id}/extract-knowledge", {}),
        ("PATCH", f"/api/v1/documents/{doc_id}/classification", {"subject_code": "english"}),
        ("GET", f"/api/v1/documents/{doc_id}/knowledge", None),
        ("GET", f"/api/v1/documents/{doc_id}/topics", None),
        ("PATCH", f"/api/v1/facts/{fact_id}", {"review_status": "rejected"}),
        ("POST", f"/api/v1/documents/{doc_id}/generate-notes", {}),
        ("GET", f"/api/v1/documents/{doc_id}/notes", None),
        ("GET", f"/api/v1/notes/{note_id}", None),
        ("POST", f"/api/v1/notes/{note_id}/regenerate", {}),
        ("PATCH", f"/api/v1/notes/{note_id}", {"understood": True}),
        ("GET", f"/api/v1/documents/{doc_id}/pyq-patterns", None),
        ("GET", f"/api/v1/documents/{doc_id}/questions", None),
        ("GET", f"/api/v1/questions/{question_id}", None),
        ("PATCH", f"/api/v1/questions/{question_id}", {"difficulty": "hard"}),
        ("DELETE", f"/api/v1/questions/{question_id}", None),
        ("GET", f"/api/v1/tests/{test_id}", None),
        ("POST", f"/api/v1/tests/{test_id}/start", None),
        ("GET", f"/api/v1/attempts/{attempt_id}/current", None),
        ("POST", f"/api/v1/attempts/{attempt_id}/submit", None),
        ("GET", f"/api/v1/attempts/{attempt_id}/results", None),
        ("GET", f"/api/v1/attempts/{attempt_id}/analysis", None),
        ("POST", f"/api/v1/attempts/{attempt_id}/improvement-plan", {}),
    ]
    for method, url, body in cross_user_checks:
        if body is not None:
            resp = client.request(method, url, json=body, headers=AUTH_B)
        else:
            resp = client.request(method, url, headers=AUTH_B)
        assert resp.status_code == 403, f"Expected 403 for {method} {url}, got {resp.status_code}"

    # Verify non-existent random UUID returns 404 (not 500)
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}", headers=AUTH_A).status_code == 404
