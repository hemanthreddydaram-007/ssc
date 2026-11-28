"""Extraction pipeline: orchestrates page extraction, OCR, chunking, and DB persistence.

Runs in a FastAPI BackgroundTask using a dedicated SQLAlchemy session factory.
Updates ProcessingJob stages and counts honestly; never fakes progress percentages.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.db.base import utcnow
from app.models.document import (
    Document,
    DocumentAsset,
    DocumentChunk,
    DocumentPage,
    ProcessingJob,
)
from app.repositories.job_repo import (
    register_active_job,
    touch_job_heartbeat,
    unregister_active_job,
)
from app.services.document_ingestion.storage import LocalPrivateStorage
from app.services.extraction.chunker import SemanticChunker
from app.services.extraction.coverage_audit import build_coverage_audit
from app.services.extraction.ocr_adapter import NullOCRAdapter, OCRAdapter
from app.services.extraction.pdf_extractor import ExtractedPage, PDFExtractor

logger = logging.getLogger(__name__)

EXTRACTION_VERSION = "v1"


def _make_initial_stages() -> list[dict[str, Any]]:
    return [
        {
            "name": "page_extraction",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
        {
            "name": "ocr_fallback",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
        {
            "name": "semantic_chunking",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
        {
            "name": "coverage_audit",
            "status": "pending",
            "processed_items": None,
            "total_items": None,
            "error_code": None,
            "error_message": None,
            "retryable": True,
        },
    ]


class ExtractionPipeline:
    """Runs page extraction, OCR fallback, semantic chunking, and coverage audit."""

    def __init__(
        self,
        storage_root: Path,
        ocr_adapter: OCRAdapter | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.ocr_adapter: OCRAdapter = ocr_adapter or NullOCRAdapter()

    def run(
        self,
        db: Session,
        document: Document,
        job: ProcessingJob,
        *,
        mode: str = "extract_only",
        force_reextract: bool = False,
        page_numbers: list[int] | None = None,
    ) -> None:
        """Execute extraction and persist results; update job status/stages throughout."""
        stages = _make_initial_stages()
        self._set_stage(stages, "page_extraction", status="running")
        self._update_job(db, job, status="running", stage="page_extraction", stages=stages)

        storage = LocalPrivateStorage(self.storage_root, db=db)
        try:
            actual_path = storage.ensure_local_file(document.storage_key)
        except (FileNotFoundError, ValueError):
            msg = (
                f"Source file is missing from storage ({document.storage_key}). "
                "If uploaded before persistent storage was enabled, please re-upload the document."
            )
            self._set_stage(
                stages,
                "page_extraction",
                status="failed",
                error_code="FILE_NOT_FOUND",
                error_message=msg,
            )
            self._fail_job(db, job, "FILE_NOT_FOUND", msg, stages=stages)
            return

        def _on_page_progress(done: int, total: int) -> None:
            if total <= 0:
                return
            if done == 1 or done % 5 == 0 or done == total:
                # Reserve the final quarter of page_extraction for DB persistence so
                # processed_items and progress_percent never reset backwards after parsing.
                extract_cap = max(1, (total * 3) // 4) if total > 1 else 0
                scaled_done = min(extract_cap, max(1, (done * 3) // 4)) if total > 1 else 0
                progress_pct = int(min(99, round(scaled_done * 100 / total)))
                self._set_stage(
                    stages,
                    "page_extraction",
                    status="running",
                    processed_items=scaled_done,
                    total_items=total,
                )
                job.progress_percent = progress_pct
                self._update_job(
                    db,
                    job,
                    status="running",
                    stage="page_extraction",
                    stages=stages,
                    processed_items=scaled_done,
                    total_items=total,
                )

        try:
            extractor = PDFExtractor(
                storage_root=self.storage_root,
                document_id=document.id,
                user_id=document.user_id,
                storage=storage,
            )
            extracted_pages = extractor.extract_all_pages(
                actual_path,
                document.source_type,
                on_page_done=_on_page_progress,
                render_ocr_pages=not isinstance(self.ocr_adapter, NullOCRAdapter),
            )
        except Exception as exc:
            self._set_stage(
                stages,
                "page_extraction",
                status="failed",
                error_code="EXTRACTION_ERROR",
                error_message=str(exc),
            )
            self._fail_job(db, job, "EXTRACTION_ERROR", str(exc), stages=stages)
            return

        if not extracted_pages:
            self._set_stage(
                stages,
                "page_extraction",
                status="failed",
                error_code="NO_PAGES",
                error_message="Extraction produced no pages",
            )
            self._fail_job(db, job, "NO_PAGES", "Extraction produced no pages", stages=stages)
            return

        total_doc_pages = len(extracted_pages)
        target_pages = extracted_pages
        if page_numbers:
            page_set = set(page_numbers)
            target_pages = [p for p in extracted_pages if p.page_number in page_set]
        elif mode == "ocr_retry":
            flagged_nums = set(
                db.execute(
                    select(DocumentPage.page_number).where(
                        DocumentPage.document_id == document.id,
                        DocumentPage.needs_ocr == True,  # noqa: E712
                    )
                )
                .scalars()
                .all()
            )
            if flagged_nums:
                target_pages = [p for p in extracted_pages if p.page_number in flagged_nums]

        if not target_pages:
            self._set_stage(
                stages,
                "page_extraction",
                status="completed",
                processed_items=0,
                total_items=0,
            )
            self._set_stage(stages, "ocr_fallback", status="skipped")
            self._set_stage(stages, "semantic_chunking", status="skipped")
            self._set_stage(
                stages, "coverage_audit", status="completed", processed_items=1, total_items=1
            )
            self._complete_job(
                db, document, job, total_items=0, stages=stages, page_count=total_doc_pages
            )
            return

        total_target = len(target_pages)
        # Keep the scaled processed_items count from _on_page_progress when persisting
        # the full document so progress_percent never jumps backwards (e.g. 31/42 -> 1/42).
        raw_processed = max(0, job.processed_items or 0)
        base_processed = raw_processed if raw_processed <= total_target else 0
        remaining_items = max(0, total_target - base_processed)
        base_pct = int(min(99, round(base_processed * 100 / total_target)))
        if (job.progress_percent or 0) < base_pct or raw_processed > total_target:
            job.progress_percent = base_pct
        self._set_stage(
            stages,
            "page_extraction",
            status="running",
            processed_items=base_processed,
            total_items=total_target,
        )
        self._update_job(
            db,
            job,
            stage="page_extraction",
            total_items=total_target,
            processed_items=base_processed,
            stages=stages,
        )

        ocr_candidate_pages = 0
        ocr_succeeded_pages = 0

        for idx, ep in enumerate(target_pages, start=1):
            self._upsert_page_and_assets(
                db,
                document=document,
                ep=ep,
                storage=storage,
                replace_assets=force_reextract,
            )
            if ep.needs_ocr:
                ocr_candidate_pages += 1

            next_processed = min(
                total_target,
                base_processed + (idx * remaining_items) // total_target,
            )
            job.processed_items = max(base_processed, next_processed)
            job.progress_percent = int(
                min(100, round(job.processed_items * 100 / total_target))
            )
            self._set_stage(
                stages,
                "page_extraction",
                status="running",
                processed_items=job.processed_items,
                total_items=total_target,
            )
            self._assign_stages(job, stages)
            db.add(job)
            db.commit()

        self._set_stage(
            stages,
            "page_extraction",
            status="completed",
            processed_items=total_target,
            total_items=total_target,
        )

        # Stage 2: OCR fallback for flagged pages
        if ocr_candidate_pages == 0:
            self._set_stage(
                stages,
                "ocr_fallback",
                status="skipped",
                processed_items=0,
                total_items=0,
            )
        else:
            self._set_stage(
                stages,
                "ocr_fallback",
                status="running",
                processed_items=0,
                total_items=ocr_candidate_pages,
            )
            self._update_job(db, job, stage="ocr_fallback", stages=stages)

            for ep in target_pages:
                if not (ep.needs_ocr and ep.page_render_bytes):
                    continue
                page_record = db.execute(
                    select(DocumentPage).where(
                        DocumentPage.document_id == document.id,
                        DocumentPage.page_number == ep.page_number,
                    )
                ).scalar_one_or_none()
                if page_record is None:
                    continue

                try:
                    ocr_result = self.ocr_adapter.extract_page(
                        ep.page_render_bytes,
                        "image/png",
                        ep.page_number,
                        document.language or "en",
                    )
                    if ocr_result.extracted_text.strip():
                        page_record.extracted_text = ocr_result.extracted_text
                        page_record.extraction_method = f"ocr_{ocr_result.ocr_provider}"
                        page_record.confidence = ocr_result.confidence
                        page_record.ocr_provider = ocr_result.ocr_provider
                        page_record.processing_status = "done"
                        page_record.needs_ocr = False
                        page_record.raw_char_count = len(
                            ocr_result.extracted_text.replace(" ", "").replace("\n", "")
                        )
                        page_record.content_hash = hashlib.sha256(
                            ocr_result.extracted_text.encode("utf-8")
                        ).hexdigest()
                        page_record.warning = ocr_result.warning
                        ocr_succeeded_pages += 1
                    else:
                        if ocr_result.warning and not page_record.warning:
                            page_record.warning = ocr_result.warning
                        if ocr_result.ocr_provider:
                            page_record.ocr_provider = ocr_result.ocr_provider
                    db.add(page_record)
                    db.commit()
                except Exception as exc:
                    logger.warning("OCR failed on page %d: %s", ep.page_number, exc)
                finally:
                    ep.page_render_bytes = None

            ocr_stage_status = (
                "completed" if ocr_succeeded_pages == ocr_candidate_pages else "skipped"
            )
            self._set_stage(
                stages,
                "ocr_fallback",
                status=ocr_stage_status,
                processed_items=ocr_succeeded_pages,
                total_items=ocr_candidate_pages,
            )

        # Stage 3: Semantic chunking across persisted pages
        self._set_stage(stages, "semantic_chunking", status="running")
        self._update_job(db, job, stage="semantic_chunking", stages=stages)
        try:
            all_db_pages = (
                db.execute(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == document.id)
                    .order_by(DocumentPage.page_number)
                )
                .scalars()
                .all()
            )
            assets = (
                db.execute(
                    select(DocumentAsset).where(DocumentAsset.document_id == document.id)
                )
                .scalars()
                .all()
            )
            assets_by_page: dict[int, list[str]] = {}
            for asset in assets:
                assets_by_page.setdefault(asset.page_number, []).append(str(asset.id))

            pages_for_chunker = [
                {
                    "page_number": p.page_number,
                    "text_blocks": [b for b in p.extracted_text.split("\n\n") if b.strip()],
                    "tables_data": p.tables_json or [],
                    "asset_ids": assets_by_page.get(p.page_number, []),
                }
                for p in all_db_pages
            ]
            chunker = SemanticChunker(
                document_id=document.id, extraction_version=EXTRACTION_VERSION
            )
            chunk_records = chunker.chunk_pages(pages_for_chunker)

            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
            db.flush()

            for idx, chunk in enumerate(chunk_records):
                db.add(
                    DocumentChunk(
                        id=chunk.id,
                        document_id=document.id,
                        chunk_index=idx,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        section_title=chunk.section_title,
                        chunk_type=chunk.chunk_type,
                        content_text=chunk.content_text,
                        asset_ids_json=chunk.asset_ids_json,
                        subject_hint=chunk.subject_hint,
                        topic_hint=chunk.topic_hint,
                        extraction_version=EXTRACTION_VERSION,
                        token_estimate=chunk.token_estimate,
                    )
                )
            db.commit()
            self._set_stage(
                stages,
                "semantic_chunking",
                status="completed",
                processed_items=len(chunk_records),
                total_items=len(chunk_records),
            )
        except Exception as exc:
            logger.exception("Chunking failed for document %s", document.id)
            self._set_stage(
                stages,
                "semantic_chunking",
                status="failed",
                error_code="CHUNKING_ERROR",
                error_message=str(exc),
            )
            self._fail_job(db, job, "CHUNKING_ERROR", str(exc), stages=stages)
            return

        # Stage 4: Deterministic Coverage Audit
        self._set_stage(stages, "coverage_audit", status="running")
        self._update_job(db, job, stage="coverage_audit", stages=stages)
        audit = build_coverage_audit(db, document.id)
        document.coverage_summary_json = audit.model_dump(mode="json")
        self._set_stage(
            stages,
            "coverage_audit",
            status="completed",
            processed_items=1,
            total_items=1,
        )

        self._complete_job(
            db,
            document,
            job,
            total_items=total_target,
            stages=stages,
            page_count=total_doc_pages,
        )
        logger.info("Extraction completed for document %s (%d pages)", document.id, total_doc_pages)

    def _upsert_page_and_assets(
        self,
        db: Session,
        *,
        document: Document,
        ep: ExtractedPage,
        storage: LocalPrivateStorage,
        replace_assets: bool,
        commit: bool = True,
    ) -> DocumentPage:
        page_text = "\n\n".join(ep.text_blocks)
        content_hash = hashlib.sha256(page_text.encode("utf-8")).hexdigest() if page_text else None
        method = "pymupdf_pdfplumber" if ep.table_count > 0 else "pymupdf"
        if document.source_type == "plain_text":
            method = "plain_text"
        elif document.source_type == "image":
            method = "image"

        existing_page = db.execute(
            select(DocumentPage).where(
                DocumentPage.document_id == document.id,
                DocumentPage.page_number == ep.page_number,
            )
        ).scalar_one_or_none()

        if existing_page is not None:
            existing_page.extracted_text = page_text
            existing_page.extraction_method = method
            existing_page.confidence = 1.0 if not ep.needs_ocr else 0.0
            existing_page.processing_status = "done" if not ep.needs_ocr else "needs_ocr"
            existing_page.needs_ocr = ep.needs_ocr
            existing_page.ocr_provider = None
            existing_page.raw_char_count = ep.raw_char_count
            existing_page.image_count = ep.image_count
            existing_page.table_count = ep.table_count
            existing_page.tables_json = ep.tables_data or None
            existing_page.content_hash = content_hash
            existing_page.warning = ep.warning
            page_record = existing_page
        else:
            page_record = DocumentPage(
                document_id=document.id,
                page_number=ep.page_number,
                extracted_text=page_text,
                extraction_method=method,
                confidence=1.0 if not ep.needs_ocr else 0.0,
                processing_status="done" if not ep.needs_ocr else "needs_ocr",
                needs_ocr=ep.needs_ocr,
                raw_char_count=ep.raw_char_count,
                image_count=ep.image_count,
                table_count=ep.table_count,
                tables_json=ep.tables_data or None,
                content_hash=content_hash,
                warning=ep.warning,
            )
        db.add(page_record)

        existing_assets = (
            db.execute(
                select(DocumentAsset).where(
                    DocumentAsset.document_id == document.id,
                    DocumentAsset.page_number == ep.page_number,
                )
            )
            .scalars()
            .all()
        )
        if replace_assets or existing_assets:
            # Remove prior asset files & rows when re-extracting a page to prevent duplicates
            for old_asset in existing_assets:
                if old_asset.storage_key != document.storage_key:
                    storage.delete(old_asset.storage_key)
                db.delete(old_asset)
            db.flush()

        for asset_dict in ep.asset_records:
            db.add(
                DocumentAsset(
                    id=asset_dict["id"],
                    document_id=document.id,
                    page_number=asset_dict["page_number"],
                    asset_type=asset_dict["asset_type"],
                    storage_key=asset_dict["storage_key"],
                    mime_type=asset_dict["mime_type"],
                    width=asset_dict["width"],
                    height=asset_dict["height"],
                    bbox_json=asset_dict.get("bbox_json"),
                )
            )

        db.commit()
        return page_record

    @staticmethod
    def _assign_stages(job: ProcessingJob, stages: list[dict[str, Any]]) -> None:
        """Assign deep-copied stage dicts and flag JSON column modified for SQLAlchemy."""
        job.stage_details_json = [dict(s) for s in stages]
        flag_modified(job, "stage_details_json")

    @staticmethod
    def _set_stage(
        stages: list[dict[str, Any]],
        name: str,
        *,
        status: str,
        processed_items: int | None = None,
        total_items: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        for stage in stages:
            if stage["name"] == name:
                stage["status"] = status
                if processed_items is not None:
                    stage["processed_items"] = processed_items
                if total_items is not None:
                    stage["total_items"] = total_items
                stage["error_code"] = error_code
                stage["error_message"] = error_message
                break

    @staticmethod
    def _update_job(
        db: Session,
        job: ProcessingJob,
        *,
        status: str | None = None,
        stage: str | None = None,
        total_items: int | None = None,
        processed_items: int | None = None,
        stages: list[dict[str, Any]] | None = None,
    ) -> None:
        touch_job_heartbeat(job.id)
        if status:
            job.status = status
            if status == "running" and not job.started_at:
                job.started_at = utcnow()
        if stage:
            job.current_stage = stage
        if total_items is not None:
            job.total_items = total_items
        if processed_items is not None:
            job.processed_items = processed_items
        if stages is not None:
            ExtractionPipeline._assign_stages(job, stages)
        db.add(job)
        db.commit()

    @staticmethod
    def _complete_job(
        db: Session,
        document: Document,
        job: ProcessingJob,
        *,
        total_items: int,
        stages: list[dict[str, Any]],
        page_count: int,
    ) -> None:
        document.status = "extracted"
        document.extraction_version = EXTRACTION_VERSION
        document.page_count = page_count
        db.add(document)

        job.status = "completed"
        job.current_stage = "done"
        job.finished_at = utcnow()
        job.total_items = total_items
        job.processed_items = total_items
        job.progress_percent = 100 if total_items > 0 else None
        ExtractionPipeline._assign_stages(job, stages)
        db.add(job)
        db.commit()

    @staticmethod
    def _fail_job(
        db: Session,
        job: ProcessingJob,
        error_code: str,
        error_message: str,
        *,
        stages: list[dict[str, Any]] | None = None,
    ) -> None:
        trimmed_msg = error_message[:2000]
        job.status = "failed"
        job.error_code = error_code
        job.error_message = trimmed_msg
        job.finished_at = utcnow()
        if stages is not None:
            ExtractionPipeline._assign_stages(job, stages)
        elif job.stage_details_json:
            updated_stages = [
                dict(s) for s in job.stage_details_json if isinstance(s, dict)
            ]
            for stage in updated_stages:
                if stage.get("status") == "running":
                    stage["status"] = "failed"
                    stage["error_code"] = error_code
                    stage["error_message"] = trimmed_msg
                    stage["retryable"] = True
            ExtractionPipeline._assign_stages(job, updated_stages)
        db.add(job)
        db.commit()
        logger.error("Extraction job %s failed: %s — %s", job.id, error_code, error_message)


def run_extraction_job_in_session(
    *,
    session_factory: sessionmaker[Session],
    storage_root: Path,
    document_id: UUID,
    job_id: UUID,
    mode: str = "extract_only",
    force_reextract: bool = False,
    page_numbers: list[int] | None = None,
) -> None:
    """Background-task entrypoint that manages its own isolated SQLAlchemy Session."""
    register_active_job(job_id)
    db = session_factory()
    try:
        document = db.get(Document, document_id)
        job = db.get(ProcessingJob, job_id)
        if document is None or document.deleted_at is not None:
            if job is not None:
                ExtractionPipeline._fail_job(
                    db, job, "DOCUMENT_NOT_FOUND", "Document was deleted or not found"
                )
            return
        if job is None:
            return

        pipeline = ExtractionPipeline(storage_root=storage_root)
        pipeline.run(
            db=db,
            document=document,
            job=job,
            mode=mode,
            force_reextract=force_reextract,
            page_numbers=page_numbers,
        )
    except Exception as exc:
        logger.exception("Unhandled error in background extraction job %s", job_id)
        job = db.get(ProcessingJob, job_id)
        if job is not None and job.status not in {"completed", "failed"}:
            ExtractionPipeline._fail_job(db, job, "UNEXPECTED_ERROR", str(exc))
    finally:
        unregister_active_job(job_id)
        db.close()
