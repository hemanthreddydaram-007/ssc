"""M8 3-PDF SSC CHSL Pilot End-to-End Simulation (`PRODUCT.md` §16).

Simulates a full realistic student workflow across 3 distinct PDF types:
  1. Text-based Quantitative Aptitude PDF (Percentages formulas, worked examples, MCQs).
  2. Table + Vector Diagram PDF (pdfplumber table + PyMuPDF vector diagram crop).
  3. Scanned / Image-only PDF (NullOCRAdapter flags needs_ocr=True -> FakeOCRAdapter retry).

Completes the full journey:
  Upload -> Extract & Coverage Audit -> Extract Knowledge -> Generate Detailed, Quick Revision &
  Strategy Notes -> Inspect Question Bank -> Build & Complete 35s Speed Challenge (with mid-test
  browser refresh + forced timeout) -> Hand-calculated Decimal score verification -> Generate
  Improvement Plan -> Launch Targeted Practice Retest -> Complete Retest -> Verify cross-attempt
  improvement delta on Performance Overview & Topic Trends.
"""

from __future__ import annotations

import io
import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.main as main_module
from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import get_llm_provider
from app.db.session import get_db
from app.schemas.notes import NoteContentJson
from app.services.assessment.timer_service import get_clock
from app.services.extraction.ocr_adapter import OCRPageResult
from app.services.notes.validators import content_text_length

AUTH_A = {"X-User-Id": "00000000-0000-0000-0000-000000000001"}


class PilotClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 27, 16, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: float = 0) -> datetime:
        self.now = self.now + timedelta(seconds=seconds)
        return self.now


class PilotOCRAdapter:
    """Deterministic OCR adapter simulating Gemini Vision OCR recovery on scanned pages."""

    provider_name = "pilot_vision_ocr"

    def extract_page(
        self,
        image_bytes: bytes,
        mime_type: str,
        page_number: int,
        language_hint: str = "en",
    ) -> OCRPageResult:
        assert len(image_bytes) > 0
        return OCRPageResult(
            page_number=page_number,
            extracted_text=(
                "PERCENTAGES SCANNED PYQ\n"
                "Q.4 A number increased by 20% becomes 180. Find the original number?\n"
                "(A) 120 (B) 140 (C) 150 (D) 160\nAnswer Key: C"
            ),
            confidence=0.93,
            ocr_provider=self.provider_name,
        )


def _pdf_1_text_maths() -> bytes:
    doc = pymupdf.open()
    try:
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(
            (50, 80),
            "SSC CHSL PERCENTAGES NOTES\n"
            "Percentage = (Part / Whole) * 100.\n"
            "Successive change formula: a + b + (a * b) / 100.\n"
            "Q.1 What is 25% of 400?\n(A) 80 (B) 100 (C) 120 (D) 140 Answer: B\n"
            "Q.2 What is 15% of 200?\n(A) 20 (B) 25 (C) 30 (D) 35 Answer: C",
        )
        return doc.tobytes()
    finally:
        doc.close()


def _pdf_2_table_and_diagram() -> bytes:
    doc = pymupdf.open()
    try:
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text((60, 70), "FRACTION TO PERCENTAGE TABLE & DIAGRAM")
        x_cols = [60, 220, 400]
        y_rows = [100, 130, 160, 190]
        shape = p1.new_shape()
        for y in y_rows:
            shape.draw_line((x_cols[0], y), (x_cols[-1], y))
        for x in x_cols:
            shape.draw_line((x, y_rows[0]), (x, y_rows[-1]))
        # Distinct geometry diagram below the table
        shape.draw_rect(pymupdf.Rect(80, 300, 240, 420))
        shape.draw_circle((160, 360), 45)
        shape.finish(color=(0, 0, 0), width=1.2)
        shape.commit()

        p1.insert_text((70, 120), "Fraction")
        p1.insert_text((230, 120), "Percentage")
        p1.insert_text((70, 150), "1/4")
        p1.insert_text((230, 150), "25%")
        p1.insert_text((70, 180), "1/5")
        p1.insert_text((230, 180), "20%")
        p1.insert_text(
            (60, 240),
            "Q.3 Convert 3/4 into percentage.\n(A) 50% (B) 60% (C) 75% (D) 80% Answer: C",
        )
        return doc.tobytes()
    finally:
        doc.close()


def _pdf_3_scanned_image_only() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (240, 240), color=(235, 235, 235)).save(buf, format="PNG")
    doc = pymupdf.open()
    try:
        p1 = doc.new_page(width=400, height=400)
        p1.insert_image(pymupdf.Rect(20, 20, 380, 380), stream=buf.getvalue())
        return doc.tobytes()
    finally:
        doc.close()


@pytest.fixture
def pilot_env(
    db_engine: Engine,
    isolated_env: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, PilotClock, MockLLMProvider], None, None]:
    testing_session_local = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)
    app = main_module.create_app()
    clock = PilotClock()
    mock_provider = MockLLMProvider()

    def _override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider

    with (
        patch(
            "httpx.HTTPTransport.handle_request",
            side_effect=AssertionError("Live HTTP/Gemini call forbidden in offline pilot!"),
        ),
        patch(
            "httpx.AsyncHTTPTransport.handle_async_request",
            side_effect=AssertionError("Live async HTTP/Gemini call forbidden in offline pilot!"),
        ),
        TestClient(app) as tc,
    ):
        yield tc, clock, mock_provider


def test_three_pdf_ssc_chsl_pilot_end_to_end(
    pilot_env: tuple[TestClient, PilotClock, MockLLMProvider],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, clock, mock_provider = pilot_env

    # ------------------------------------------------------------------
    # Phase 1: Upload & Extract 3 distinct PDFs + Coverage Audits
    # ------------------------------------------------------------------
    d1_id = client.post(
        "/api/v1/documents",
        files={"file": ("01_maths_percentages.pdf", _pdf_1_text_maths(), "application/pdf")},
        data={"title": "Maths Percentages", "subject_code": "quantitative_aptitude"},
        headers=AUTH_A,
    ).json()["id"]
    d2_id = client.post(
        "/api/v1/documents",
        files={"file": ("02_table_diagram.pdf", _pdf_2_table_and_diagram(), "application/pdf")},
        data={"title": "Fraction Table & Diagram", "subject_code": "quantitative_aptitude"},
        headers=AUTH_A,
    ).json()["id"]
    d3_id = client.post(
        "/api/v1/documents",
        files={"file": ("03_scanned_pyq.pdf", _pdf_3_scanned_image_only(), "application/pdf")},
        data={"title": "Scanned PYQ Sheet", "subject_code": "quantitative_aptitude"},
        headers=AUTH_A,
    ).json()["id"]

    assert (
        client.post(f"/api/v1/documents/{d1_id}/process", json={}, headers=AUTH_A).status_code
        == 202
    )
    assert (
        client.post(f"/api/v1/documents/{d2_id}/process", json={}, headers=AUTH_A).status_code
        == 202
    )
    assert (
        client.post(f"/api/v1/documents/{d3_id}/process", json={}, headers=AUTH_A).status_code
        == 202
    )

    cov2 = client.get(f"/api/v1/documents/{d2_id}/coverage", headers=AUTH_A).json()
    assert cov2["tables_extracted"] >= 1
    assert cov2["images_extracted"] >= 1

    # Scanned PDF 3 initially flagged needs_ocr=True under NullOCRAdapter
    cov3_before = client.get(f"/api/v1/documents/{d3_id}/coverage", headers=AUTH_A).json()
    assert cov3_before["pages_requiring_ocr"] == 1

    # Retry OCR on PDF 3 with PilotOCRAdapter
    monkeypatch.setattr(
        "app.services.extraction.extraction_pipeline.ExtractionPipeline.__init__",
        lambda self, storage_root, ocr_adapter=None: (
            setattr(self, "storage_root", storage_root)
            or setattr(self, "ocr_adapter", ocr_adapter or PilotOCRAdapter())
        ),
    )
    assert (
        client.post(
            f"/api/v1/documents/{d3_id}/process",
            json={"mode": "ocr_retry"},
            headers=AUTH_A,
        ).status_code
        == 202
    )
    cov3_after = client.get(f"/api/v1/documents/{d3_id}/coverage", headers=AUTH_A).json()
    assert cov3_after["pages_extracted_ocr"] == 1
    assert cov3_after["pages_requiring_ocr"] == 0

    # ------------------------------------------------------------------
    # Phase 2: Extract Knowledge -> Question Bank + Notes across all 3 PDFs
    # ------------------------------------------------------------------
    # Script deterministic questions across the 3 documents (6 total verified MCQs)
    def _enqueue_doc_knowledge(questions: list[dict], fact_text: str, excerpt: str) -> None:
        mock_provider.enqueue_raw(
            json.dumps(
                {
                    "subject_code": "quantitative_aptitude",
                    "material_type": "pyq_paper",
                    "language": "en",
                    "confidence": 0.95,
                    "topic_candidates": ["Percentages"],
                    "rationale": "Percentages formulas and PYQs.",
                }
            ),
            prompt_name="document_classification",
        )
        mock_provider.enqueue_raw(
            json.dumps(
                {
                    "detected_subject_code": "quantitative_aptitude",
                    "facts": [
                        {
                            "fact_type": "formula",
                            "content": fact_text,
                            "topic_name": "Percentages",
                            "source_page_number": 1,
                            "supporting_excerpt": excerpt,
                            "provenance": "extracted",
                            "confidence": 0.95,
                        }
                    ],
                    "concepts": [
                        {
                            "title": "Percentage Fundamentals",
                            "explanation": fact_text,
                            "topic_name": "Percentages",
                            "difficulty": "easy",
                            "source_page_number": 1,
                            "supporting_excerpt": excerpt,
                            "provenance": "extracted",
                            "confidence": 0.92,
                        }
                    ],
                    "questions": questions,
                }
            ),
            prompt_name="knowledge_extraction",
        )

    def _q(stem: str, opts: list[str], ans: str, excerpt: str) -> dict:
        return {
            "question_text": stem,
            "question_type": "single_choice",
            "subject_code": "quantitative_aptitude",
            "topic_name": "Percentages",
            "difficulty": "easy",
            "options": [
                {"key": k, "text": t} for k, t in zip(("A", "B", "C", "D"), opts, strict=True)
            ],
            "correct_option_key": ans,
            "explanation": f"Verified answer is {ans}.",
            "source_page_number": 1,
            "supporting_excerpt": excerpt,
            "answer_key_provenance": "source_answer_key",
        }

    # PDF 1 (has 1 prose chunk -> emits Q1, Q2, plus 2 extra valid PYQs for >=5 topic sample)
    _enqueue_doc_knowledge(
        [
            _q("What is 25% of 400?", ["80", "100", "120", "140"], "B", "What is 25% of 400?"),
            _q("What is 15% of 200?", ["20", "25", "30", "35"], "C", "What is 15% of 200?"),
            _q("What is 10% of 500?", ["40", "50", "60", "70"], "B", "Percentage = (Part / Whole)"),
            _q("What is 50% of 120?", ["50", "60", "70", "80"], "B", "Percentage = (Part / Whole)"),
        ],
        "Percentage = (Part / Whole) * 100.",
        "Percentage = (Part / Whole) * 100.",
    )
    assert (
        client.post(f"/api/v1/documents/{d1_id}/extract-knowledge", headers=AUTH_A).status_code
        == 202
    )

    # PDF 2 (note: table+prose creates 2 chunks, script classification + chunk 1)
    _enqueue_doc_knowledge(
        [_q("Convert 3/4 into percentage.", ["50%", "60%", "75%", "80%"], "C", "Convert 3/4")],
        "1/4 equals 25%.",
        "1/4",
    )
    assert (
        client.post(f"/api/v1/documents/{d2_id}/extract-knowledge", headers=AUTH_A).status_code
        == 202
    )

    # PDF 3 (scanned OCR'd text)
    _enqueue_doc_knowledge(
        [
            _q(
                "A number increased by 20% becomes 180. Find the original number?",
                ["120", "140", "150", "160"],
                "C",
                "increased by 20% becomes 180",
            )
        ],
        "Successive percentage base multiplier.",
        "increased by 20% becomes 180",
    )
    assert (
        client.post(f"/api/v1/documents/{d3_id}/extract-knowledge", headers=AUTH_A).status_code
        == 202
    )

    # Generate Smart Notes on PDF 1 (detailed, quick_revision, strategy_sheet)
    notes_job = client.post(
        f"/api/v1/documents/{d1_id}/generate-notes",
        json={"note_types": ["detailed", "quick_revision", "strategy_sheet"]},
        headers=AUTH_A,
    )
    assert notes_job.status_code == 202
    doc1_notes = client.get(f"/api/v1/documents/{d1_id}/notes", headers=AUTH_A).json()["items"]
    assert len(doc1_notes) == 3
    by_type = {n["note_type"]: n for n in doc1_notes}
    d_note = client.get(f"/api/v1/notes/{by_type['detailed']['id']}", headers=AUTH_A).json()
    q_note = client.get(f"/api/v1/notes/{by_type['quick_revision']['id']}", headers=AUTH_A).json()
    assert content_text_length(
        NoteContentJson.model_validate(q_note["content_json"])
    ) < content_text_length(NoteContentJson.model_validate(d_note["content_json"]))

    # Inspect Question Bank -> verify >= 5 verified Percentages questions across PDFs
    bank = client.get(
        "/api/v1/questions",
        params={"subject_code": "quantitative_aptitude", "validation_status": "verified"},
        headers=AUTH_A,
    ).json()
    assert bank["total"] >= 5
    selected_q_ids = [item["id"] for item in bank["items"][:5]]
    topics_list = client.get("/api/v1/topics", headers=AUTH_A).json()["items"]
    pct_topic_id = next(t["id"] for t in topics_list if t["name"] == "Percentages")

    # ------------------------------------------------------------------
    # Phase 3: Build & Complete 35s Speed Challenge (with Refresh & Timeout)
    # ------------------------------------------------------------------
    test1 = client.post(
        "/api/v1/tests",
        json={
            "title": "Pilot Attempt 1 — 35s Speed Challenge",
            "question_ids": selected_q_ids,
            "question_count": 5,
            "timer_mode": "speed_challenge",
            "per_question_seconds": 35,
            "points_per_question": "2.00",
            "negative_marking_enabled": True,
            "negative_points": "0.50",
        },
        headers=AUTH_A,
    ).json()
    att1 = client.post(f"/api/v1/tests/{test1['id']}/start", headers=AUTH_A).json()
    att1_id = att1["attempt_id"]

    # Simulated mid-test browser refresh at t+15s on Q0
    clock.advance(seconds=15)
    refreshed = client.get(f"/api/v1/attempts/{att1_id}/current", headers=AUTH_A).json()
    assert refreshed["current_question"]["question_remaining_seconds"] == 20

    # Q0: Correct (+2.00)
    # Q1: Forced timeout (>35s + 1500ms -> 0.00)
    # Q2, Q3, Q4: Incorrect (-0.50 each) -> 1 correct, 3 incorrect, 1 timed_out
    # Hand-calculated score = 2.00 - 1.50 = 0.50 / 10.00; accuracy (answered) = 1/4 = 25.00%
    def _correct_key_for(stem: str) -> str:
        if "25% of 400" in stem or "10% of 500" in stem or "50% of 120" in stem:
            return "B"
        return "C"

    for idx in range(5):
        cur = client.get(f"/api/v1/attempts/{att1_id}/current", headers=AUTH_A).json()
        cur_q = cur["current_question"]
        right_key = _correct_key_for(cur_q["question_text"])
        wrong_key = "A"

        if idx == 1:
            clock.advance(seconds=37)
            late = client.post(
                f"/api/v1/attempts/{att1_id}/responses",
                json={
                    "test_question_id": cur_q["test_question_id"],
                    "selected_option_key": right_key,
                    "action": "answer",
                },
                headers=AUTH_A,
            )
            assert late.status_code == 409
            assert late.json()["code"] == "QUESTION_TIMED_OUT"
        else:
            clock.advance(seconds=10)
            chosen = right_key if idx == 0 else wrong_key
            res = client.post(
                f"/api/v1/attempts/{att1_id}/responses",
                json={
                    "test_question_id": cur_q["test_question_id"],
                    "selected_option_key": chosen,
                    "action": "answer",
                },
                headers=AUTH_A,
            )
            assert res.status_code == 200

    sub1 = client.post(f"/api/v1/attempts/{att1_id}/submit", headers=AUTH_A).json()
    assert Decimal(sub1["total_score"]) == Decimal("0.50")
    assert Decimal(sub1["max_score"]) == Decimal("10.00")
    assert sub1["correct_count"] == 1
    assert sub1["incorrect_count"] == 3
    assert sub1["timed_out_count"] == 1

    res1 = client.get(f"/api/v1/attempts/{att1_id}/results", headers=AUTH_A).json()
    assert Decimal(res1["accuracy_attempted_percent"]) == Decimal("25.00")

    # ------------------------------------------------------------------
    # Phase 4: Improvement Plan -> Targeted Practice Retest -> Improvement Delta
    # ------------------------------------------------------------------
    plan = client.post(
        f"/api/v1/attempts/{att1_id}/improvement-plan",
        json={"include_ai_coaching": False},
        headers=AUTH_A,
    ).json()
    assert len(plan["recommendations"]) >= 1
    assert any(r["action_type"] == "concept_revision" for r in plan["recommendations"])

    tp = client.post(
        "/api/v1/performance/targeted-practice",
        json={"topic_ids": [pct_topic_id], "question_count": 5, "timer_mode": "learning_mode"},
        headers=AUTH_A,
    )
    assert tp.status_code == 201
    retest_id = tp.json()["test"]["id"]

    att2 = client.post(f"/api/v1/tests/{retest_id}/start", headers=AUTH_A).json()
    att2_id = att2["attempt_id"]
    for idx in range(5):
        if idx > 0:
            client.post(
                f"/api/v1/attempts/{att2_id}/navigate",
                json={"target_index": idx},
                headers=AUTH_A,
            )
        cur = client.get(f"/api/v1/attempts/{att2_id}/current", headers=AUTH_A).json()[
            "current_question"
        ]
        clock.advance(seconds=8)
        client.post(
            f"/api/v1/attempts/{att2_id}/responses",
            json={
                "test_question_id": cur["test_question_id"],
                "selected_option_key": _correct_key_for(cur["question_text"]),
                "action": "answer",
            },
            headers=AUTH_A,
        )
    sub2 = client.post(f"/api/v1/attempts/{att2_id}/submit", headers=AUTH_A).json()
    assert Decimal(sub2["total_score"]) == Decimal("10.00")

    # Verify cross-attempt improvement delta on Performance Overview & Trends
    trends = client.get(f"/api/v1/performance/topics/{pct_topic_id}/trends", headers=AUTH_A).json()
    assert len(trends["points"]) == 2
    assert Decimal(trends["points"][0]["accuracy_percent"]) == Decimal("25.00")
    assert Decimal(trends["points"][1]["accuracy_percent"]) == Decimal("100.00")

    att2_analysis = client.get(f"/api/v1/attempts/{att2_id}/analysis", headers=AUTH_A).json()
    assert Decimal(att2_analysis["comparison_to_previous"][0]["accuracy_delta_percent"]) == Decimal(
        "75.00"
    )

    overview = client.get("/api/v1/performance/overview", headers=AUTH_A).json()
    assert overview["total_attempts"] == 2
    assert len(overview["recent_improvement_deltas"]) >= 1
    # Cumulative accuracy jumped from 25.00% (1/4) to 66.67% (6/9) -> +41.67%
    assert Decimal(overview["recent_improvement_deltas"][0]["accuracy_delta_percent"]) == Decimal(
        "41.67"
    )
