from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.prompts.classification import CLASSIFICATION_PROMPT_V1
from app.ai.provider import LLMProvider, LLMResult
from app.ai.schemas.classification import DocumentClassificationOutput
from app.models.document import Document, DocumentChunk, DocumentPage
from app.models.learning import AIGenerationRun
from app.repositories.knowledge_repo import KnowledgeRepository

logger = logging.getLogger(__name__)

MIN_CLASSIFICATION_CONFIDENCE = 0.50


@dataclass(slots=True)
class ClassificationOutcome:
    """Result returned by `DocumentClassifier.classify_document`."""

    detected_subject_code: str
    effective_subject_code: str
    material_type: str
    language: str
    confidence: float
    topic_candidates: list[str]
    generation_run_id: object | None = None


class DocumentClassifier:
    """Classifies document subject, material type, and language via `LLMProvider`."""

    def __init__(self, db: Session, llm_provider: LLMProvider) -> None:
        self.db = db
        self.llm_provider = llm_provider
        self.repo = KnowledgeRepository(db)

    @staticmethod
    def _build_sample_text(
        pages: list[DocumentPage], chunks: list[DocumentChunk], max_chars: int = 3500
    ) -> str:
        parts: list[str] = []
        total = 0
        if chunks:
            for chunk in chunks[:4]:
                snippet = f"[PAGES {chunk.page_start}-{chunk.page_end}]\n{chunk.content_text}"
                parts.append(snippet)
                total += len(snippet)
                if total >= max_chars:
                    break
        else:
            for page in pages[:3]:
                if page.extracted_text.strip():
                    snippet = f"[PAGE {page.page_number}]\n{page.extracted_text}"
                    parts.append(snippet)
                    total += len(snippet)
                    if total >= max_chars:
                        break
        return "\n\n".join(parts)[:max_chars]

    def classify_document(
        self,
        document: Document,
        *,
        pages: list[DocumentPage],
        chunks: list[DocumentChunk],
        exam_code: str = "ssc_chsl_tier_1",
        job_id: object | None = None,
    ) -> ClassificationOutcome:
        sample_text = self._build_sample_text(pages, chunks)
        prompt = CLASSIFICATION_PROMPT_V1.render(
            title=document.title,
            subject_hint=document.subject_code or document.chapter_or_topic_hint or "none",
            material_type_hint=document.material_type or "other",
            exam_code=exam_code,
            sample_text=sample_text or "(no readable text extracted)",
        )

        result: LLMResult[DocumentClassificationOutput] = (
            self.llm_provider.generate_structured_output(
                DocumentClassificationOutput,
                prompt,
                system_instruction=CLASSIFICATION_PROMPT_V1.system_instruction,
                model_tier="fast",
                temperature=0.1,
                prompt_name=CLASSIFICATION_PROMPT_V1.name,
                prompt_version=CLASSIFICATION_PROMPT_V1.version,
            )
        )

        run = AIGenerationRun(
            document_id=document.id,
            job_id=job_id,  # type: ignore[arg-type]
            stage="classification",
            model_name=result.model_name,
            prompt_name=result.prompt_name,
            prompt_version=result.prompt_version,
            latency_ms=result.latency_ms,
            token_usage_json=result.token_usage,
            validation_status=result.status,
            error_message=result.error_message,
        )
        self.repo.record_generation_run(run)

        if result.parsed is None or result.status == "failed_validation":
            detected_subject = "unknown"
            confidence = 0.0
            material_type = document.material_type or "other"
            language = document.language or "en"
            topic_candidates: list[str] = []
        else:
            parsed = result.parsed
            confidence = float(parsed.confidence)
            # Never force a subject guess when confidence is below threshold
            detected_subject = (
                parsed.subject_code if confidence >= MIN_CLASSIFICATION_CONFIDENCE else "unknown"
            )
            material_type = parsed.material_type
            language = parsed.language
            topic_candidates = list(parsed.topic_candidates)

        document.detected_subject_code = detected_subject
        document.classification_confidence = confidence
        if not document.subject_code:
            document.subject_code = detected_subject
        if document.material_type in ("", "other") and material_type != "other":
            document.material_type = material_type
        if not document.language and language:
            document.language = language

        self.db.add(document)
        self.db.flush()

        effective_subject = document.subject_code or detected_subject
        return ClassificationOutcome(
            detected_subject_code=detected_subject,
            effective_subject_code=effective_subject,
            material_type=document.material_type,
            language=document.language,
            confidence=confidence,
            topic_candidates=topic_candidates,
            generation_run_id=run.id,
        )
