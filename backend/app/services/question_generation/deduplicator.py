from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from rapidfuzz import fuzz


def normalize_stem(text: str) -> str:
    """Normalize question stem whitespace and casing for duplicate detection."""
    return " ".join(text.split()).strip().lower()


def compute_stem_hash(question_text: str) -> str:
    """Return a deterministic SHA-256 hash of the normalized question stem."""
    return hashlib.sha256(normalize_stem(question_text).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class DuplicateCheckResult:
    """Outcome of exact hash and fuzzy near-duplicate stem detection."""

    is_duplicate: bool
    reason: str | None = None
    matched_question_id: UUID | None = None
    similarity: float = 0.0


class QuestionDeduplicator:
    """Detects exact and near-duplicate question stems using SHA-256 + RapidFuzz."""

    def __init__(
        self,
        existing_entries: Sequence[tuple[UUID | None, str, str]] = (),
        *,
        similarity_threshold: float = 90.0,
    ) -> None:
        self._similarity_threshold = similarity_threshold
        self._entries: list[tuple[UUID | None, str, str]] = []
        self._hashes: dict[str, UUID | None] = {}
        for q_id, stem_hash, stem_text in existing_entries:
            self.register(q_id, stem_hash, stem_text)

    def register(self, question_id: UUID | None, stem_hash: str, question_text: str) -> None:
        """Add a question stem to the in-memory index for batch deduplication."""
        norm = normalize_stem(question_text)
        self._hashes.setdefault(stem_hash, question_id)
        self._entries.append((question_id, stem_hash, norm))

    def check(self, question_text: str) -> DuplicateCheckResult:
        """Return DuplicateCheckResult indicating exact or near-duplicate match."""
        norm = normalize_stem(question_text)
        stem_hash = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        if stem_hash in self._hashes:
            return DuplicateCheckResult(
                is_duplicate=True,
                reason="exact_stem_hash",
                matched_question_id=self._hashes[stem_hash],
                similarity=100.0,
            )

        for q_id, _h, existing_norm in self._entries:
            if not existing_norm:
                continue
            ratio = float(fuzz.ratio(norm, existing_norm))
            token_ratio = float(fuzz.token_sort_ratio(norm, existing_norm))
            if ratio >= self._similarity_threshold or (
                token_ratio >= 94.0 and abs(len(norm) - len(existing_norm)) <= 12
            ):
                return DuplicateCheckResult(
                    is_duplicate=True,
                    reason="near_duplicate_stem",
                    matched_question_id=q_id,
                    similarity=max(ratio, token_ratio),
                )

        return DuplicateCheckResult(is_duplicate=False)
