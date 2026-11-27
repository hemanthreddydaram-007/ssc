from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any
from uuid import UUID

from rapidfuzz import fuzz

from app.models.learning import Concept, Fact
from app.repositories.knowledge_repo import KnowledgeRepository

_WS_RE = re.compile(r"\s+")
_PUNCT_TRIM_RE = re.compile(r"^[\s.,;:!?]+|[\s.,;:!?]+$")
_NUM_TOKEN_RE = re.compile(r"\d+(?:[.,:/-]\d+)*%?")


def normalize_for_hash(text: str) -> str:
    """Normalize whitespace, casing, and outer punctuation for deterministic hashing."""
    collapsed = _WS_RE.sub(" ", text).strip().lower()
    return _PUNCT_TRIM_RE.sub("", collapsed)


def compute_canonical_hash(*parts: str) -> str:
    """Compute SHA-256 hex digest for canonical deduplication keys."""
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def extract_numeric_tokens(text: str) -> tuple[str, ...]:
    """Extract numeric/date/percentage tokens to detect conflicting factual values."""
    return tuple(_NUM_TOKEN_RE.findall(text))


def _strip_numeric_tokens(text: str) -> str:
    cleaned = _NUM_TOKEN_RE.sub(" <NUM> ", text.lower())
    return _WS_RE.sub(" ", cleaned).strip()


def _merge_source_refs(
    existing_refs: list[Any], new_ref: dict[str, Any]
) -> list[Any]:
    refs = list(existing_refs or [])
    new_key = (
        new_ref.get("document_id"),
        new_ref.get("page_number"),
        new_ref.get("chunk_id"),
        new_ref.get("supporting_excerpt"),
    )
    for item in refs:
        if not isinstance(item, dict):
            continue
        item_key = (
            item.get("document_id"),
            item.get("page_number"),
            item.get("chunk_id"),
            item.get("supporting_excerpt"),
        )
        if item_key == new_key:
            return refs
    refs.append(new_ref)
    return refs


def _is_conflicting_fact(existing_content: str, new_content: str) -> bool:
    """Detect whether two facts describe the same subject with conflicting values."""
    nums_existing = extract_numeric_tokens(existing_content)
    nums_new = extract_numeric_tokens(new_content)
    if nums_existing and nums_new and nums_existing != nums_new:
        skeleton_existing = _strip_numeric_tokens(existing_content)
        skeleton_new = _strip_numeric_tokens(new_content)
        if fuzz.token_sort_ratio(skeleton_existing, skeleton_new) >= 70.0:
            return True
    return False


def upsert_fact(
    repo: KnowledgeRepository,
    *,
    document_id: UUID,
    topic_id: UUID | None,
    chunk_id: UUID | None,
    fact_type: str,
    content: str,
    provenance: str,
    confidence: float,
    source_page_number: int | None,
    supporting_excerpt: str | None,
    is_time_sensitive: bool,
    source_date_label: str | None,
    review_status: str,
    model_name: str | None,
    prompt_name: str | None,
    prompt_version: str | None,
    generation_run_id: UUID | None,
) -> Fact:
    """Persist a fact while deduplicating identical facts and flagging conflicting values."""
    norm_content = normalize_for_hash(content)
    canonical_hash = compute_canonical_hash(
        str(document_id),
        str(topic_id or ""),
        fact_type,
        norm_content,
    )

    new_ref = {
        "document_id": str(document_id),
        "page_number": source_page_number,
        "chunk_id": str(chunk_id) if chunk_id else None,
        "supporting_excerpt": supporting_excerpt,
        "provenance": provenance,
    }

    exact = repo.find_fact_by_canonical_hash(document_id, canonical_hash)
    if exact is not None:
        exact.source_refs_json = _merge_source_refs(exact.source_refs_json, new_ref)
        exact.confidence = max(exact.confidence, confidence)
        if exact.review_status != "conflict" and review_status == "verified":
            exact.review_status = "verified"
        repo.db.add(exact)
        repo.db.flush()
        return exact

    candidates = repo.find_facts_by_type_scope(document_id, topic_id, fact_type)
    conflict_group: UUID | None = None

    for existing in candidates:
        existing_norm = normalize_for_hash(existing.content)
        similarity = fuzz.token_sort_ratio(existing_norm, norm_content)
        same_nums = extract_numeric_tokens(existing.content) == extract_numeric_tokens(content)

        if similarity >= 92.0 and same_nums:
            existing.source_refs_json = _merge_source_refs(existing.source_refs_json, new_ref)
            existing.confidence = max(existing.confidence, confidence)
            if existing.review_status != "conflict" and review_status == "verified":
                existing.review_status = "verified"
            repo.db.add(existing)
            repo.db.flush()
            return existing

        if _is_conflicting_fact(existing.content, content):
            conflict_group = existing.conflict_group_id or uuid.uuid4()
            existing.conflict_group_id = conflict_group
            existing.review_status = "conflict"
            repo.db.add(existing)
            break

    final_status = "conflict" if conflict_group is not None else review_status
    fact = Fact(
        document_id=document_id,
        topic_id=topic_id,
        chunk_id=chunk_id,
        fact_type=fact_type,
        content=content.strip(),
        provenance=provenance,
        confidence=confidence,
        source_page_number=source_page_number,
        supporting_excerpt=supporting_excerpt,
        source_refs_json=[new_ref],
        canonical_hash=canonical_hash,
        conflict_group_id=conflict_group,
        is_time_sensitive=is_time_sensitive,
        source_date_label=source_date_label,
        review_status=final_status,
        model_name=model_name,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        generation_run_id=generation_run_id,
    )
    repo.db.add(fact)
    repo.db.flush()
    return fact


def upsert_concept(
    repo: KnowledgeRepository,
    *,
    document_id: UUID,
    topic_id: UUID | None,
    title: str,
    explanation: str,
    difficulty: str | None,
    provenance: str,
    confidence: float,
    review_status: str,
    source_page_number: int | None,
    chunk_id: UUID | None,
    supporting_excerpt: str | None,
    prerequisites: list[str],
    related_concepts: list[str],
    model_name: str | None,
    prompt_name: str | None,
    prompt_version: str | None,
    generation_run_id: UUID | None,
) -> Concept:
    """Persist a concept while merging provenance across duplicate occurrences."""
    canonical_hash = compute_canonical_hash(
        str(document_id),
        str(topic_id or ""),
        normalize_for_hash(title),
    )
    new_ref = {
        "document_id": str(document_id),
        "page_number": source_page_number,
        "chunk_id": str(chunk_id) if chunk_id else None,
        "supporting_excerpt": supporting_excerpt,
        "provenance": provenance,
    }

    existing = repo.find_concept_by_canonical_hash(document_id, canonical_hash)
    if existing is not None:
        existing.source_refs_json = _merge_source_refs(existing.source_refs_json, new_ref)
        existing.confidence = max(existing.confidence, confidence)
        if len(explanation.strip()) > len(existing.explanation):
            existing.explanation = explanation.strip()
        if review_status == "verified" and existing.review_status == "needs_review":
            existing.review_status = "verified"
        repo.db.add(existing)
        repo.db.flush()
        return existing

    concept = Concept(
        document_id=document_id,
        topic_id=topic_id,
        title=title.strip()[:255],
        explanation=explanation.strip(),
        difficulty=difficulty,
        provenance=provenance,
        confidence=confidence,
        review_status=review_status,
        source_refs_json=[new_ref],
        prerequisites_json=list(prerequisites),
        related_concept_ids_json=list(related_concepts),
        canonical_hash=canonical_hash,
        model_name=model_name,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        generation_run_id=generation_run_id,
    )
    repo.db.add(concept)
    repo.db.flush()
    return concept
