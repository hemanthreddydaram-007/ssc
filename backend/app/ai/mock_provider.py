from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel

from app.ai.provider import BaseLLMProvider, ModelTier, _RawProviderResponse
from app.ai.schemas.classification import DocumentClassificationOutput
from app.ai.schemas.common import QuestionVerificationResult
from app.ai.schemas.extraction import (
    ChunkExtractionOutput,
    ExtractedConceptItem,
    ExtractedFactItem,
    ExtractedOptionItem,
    ExtractedQuestionItem,
)
from app.ai.schemas.notes import (
    GeneratedNoteBlock,
    GeneratedNoteOutput,
    GeneratedNoteSection,
    GeneratedSourceRefItem,
    NoteBlockMetadataItem,
)

ResponseHandler = Callable[[str], str]


class MockLLMProvider(BaseLLMProvider):
    """Deterministic in-memory `LLMProvider` for offline unit and integration tests."""

    def __init__(
        self,
        *,
        model_name: str = "mock-gemini-2.5-flash",
        scripted_responses: Sequence[str] = (),
    ) -> None:
        self.model_name = model_name
        self._queue: deque[str] = deque(scripted_responses)
        self._handlers: dict[str, deque[str | ResponseHandler]] = {}
        self.calls: list[dict[str, Any]] = []

    def enqueue_raw(self, raw_text: str, *, prompt_name: str | None = None) -> None:
        """Queue a raw JSON/text string (globally or keyed by `prompt_name`)."""
        if prompt_name is None:
            self._queue.append(raw_text)
        else:
            self._handlers.setdefault(prompt_name, deque()).append(raw_text)

    def register_handler(self, prompt_name: str, handler: ResponseHandler) -> None:
        """Register a deterministic callable for a specific `prompt_name`."""
        self._handlers.setdefault(prompt_name, deque()).append(handler)

    def _pop_scripted(self, prompt_name: str, prompt: str) -> str | None:
        if prompt_name in self._handlers and self._handlers[prompt_name]:
            entry = self._handlers[prompt_name].popleft()
            if callable(entry):
                return entry(prompt)
            return entry
        if self._queue:
            return self._queue.popleft()
        return None

    def _invoke_structured(
        self,
        schema: type[BaseModel],
        prompt: str,
        *,
        context_parts: Sequence[Any],
        system_instruction: str | None,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str,
        prompt_version: str,
    ) -> _RawProviderResponse:
        self.calls.append(
            {
                "kind": "structured",
                "schema": schema.__name__,
                "prompt_name": prompt_name,
                "prompt_version": prompt_version,
                "model_tier": model_tier,
                "prompt": prompt,
            }
        )

        scripted = self._pop_scripted(prompt_name, prompt)
        if scripted is not None:
            raw_text = scripted
        elif schema is DocumentClassificationOutput:
            raw_text = self._default_classification(prompt)
        elif schema is ChunkExtractionOutput:
            raw_text = self._default_extraction(prompt)
        elif schema is QuestionVerificationResult:
            raw_text = QuestionVerificationResult(
                is_valid=True,
                confidence=0.9,
                issues=[],
                reasoning="Verified by MockLLMProvider.",
            ).model_dump_json()
        elif schema is GeneratedNoteOutput:
            raw_text = self._default_notes(prompt, prompt_name)
        else:
            raw_text = "{}"

        return _RawProviderResponse(
            raw_text=raw_text,
            model_name=self.model_name,
            token_usage={
                "input_tokens": max(1, len(prompt) // 4),
                "output_tokens": max(1, len(raw_text) // 4),
                "total_tokens": max(2, (len(prompt) + len(raw_text)) // 4),
            },
        )

    def _invoke_text(
        self,
        prompt: str,
        *,
        context: str | None,
        system_instruction: str | None,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str,
        prompt_version: str,
    ) -> _RawProviderResponse:
        self.calls.append(
            {
                "kind": "text",
                "prompt_name": prompt_name,
                "prompt_version": prompt_version,
                "model_tier": model_tier,
                "prompt": prompt,
            }
        )
        scripted = self._pop_scripted(prompt_name, prompt)
        raw_text = scripted if scripted is not None else f"[mock:{prompt_name}] {prompt[:160]}"
        return _RawProviderResponse(
            raw_text=raw_text,
            model_name=self.model_name,
            token_usage={
                "input_tokens": max(1, len(prompt) // 4),
                "output_tokens": max(1, len(raw_text) // 4),
                "total_tokens": max(2, (len(prompt) + len(raw_text)) // 4),
            },
        )

    @staticmethod
    def _infer_subject(text: str) -> tuple[str, float, list[str]]:
        lowered = text.lower()
        scores: dict[str, int] = {
            "quantitative_aptitude": sum(
                1
                for kw in (
                    "percentage",
                    "profit",
                    "loss",
                    "ratio",
                    "time and work",
                    "algebra",
                    "geometry",
                    "trigonometry",
                    "interest",
                    "speed",
                    "average",
                )
                if kw in lowered
            ),
            "reasoning": sum(
                1
                for kw in (
                    "syllogism",
                    "coding-decoding",
                    "analogy",
                    "blood relation",
                    "seating",
                    "series",
                    "mirror image",
                    "direction sense",
                )
                if kw in lowered
            ),
            "english": sum(
                1
                for kw in (
                    "grammar",
                    "synonym",
                    "antonym",
                    "idiom",
                    "preposition",
                    "tense",
                    "active voice",
                    "passive voice",
                    "comprehension",
                    "subject-verb",
                )
                if kw in lowered
            ),
            "general_awareness": sum(
                1
                for kw in (
                    "constitution",
                    "article",
                    "amendment",
                    "river",
                    "capital",
                    "ministry",
                    "dynasty",
                    "battle",
                    "current affairs",
                    "scheme",
                    "gdp",
                )
                if kw in lowered
            ),
        }
        best_subject = max(scores, key=lambda k: scores[k])
        best_hits = scores[best_subject]
        if best_hits == 0:
            return "unknown", 0.35, []
        confidence = min(0.95, 0.65 + 0.08 * best_hits)
        topics = [best_subject.replace("_", " ").title()]
        return best_subject, round(confidence, 2), topics

    def _default_classification(self, prompt: str) -> str:
        subject, confidence, topics = self._infer_subject(prompt)
        lowered = prompt.lower()
        material_type = "other"
        if "(a)" in lowered and "(b)" in lowered:
            material_type = "pyq_paper"
        elif "notes" in lowered or "formula" in lowered:
            material_type = "notes"
        return DocumentClassificationOutput(
            subject_code=subject,  # type: ignore[arg-type]
            material_type=material_type,  # type: ignore[arg-type]
            language="en",
            confidence=confidence,
            topic_candidates=topics,
            rationale="Deterministic keyword classification from MockLLMProvider.",
        ).model_dump_json()

    def _default_extraction(self, prompt: str) -> str:
        chunk_match = re.search(r"Chunk text:\n(.*)", prompt, re.DOTALL)
        chunk_text = chunk_match.group(1).strip() if chunk_match else prompt
        subject, _, _ = self._infer_subject(chunk_text)

        page_match = re.search(r"\[PAGE\s+(\d+)\]", chunk_text)
        page_num = int(page_match.group(1)) if page_match else 1

        clean_lines = [
            ln.strip()
            for ln in chunk_text.splitlines()
            if ln.strip() and not ln.strip().startswith("[PAGE ")
        ]
        excerpt = clean_lines[0][:240] if clean_lines else ""

        facts: list[ExtractedFactItem] = []
        concepts: list[ExtractedConceptItem] = []
        questions: list[ExtractedQuestionItem] = []

        topic_label = (
            "General Concepts" if subject == "unknown" else subject.replace("_", " ").title()
        )
        if excerpt:
            fact_type = "formula" if ("=" in excerpt or "%" in excerpt) else "definition"
            facts.append(
                ExtractedFactItem(
                    fact_type=fact_type,  # type: ignore[arg-type]
                    content=excerpt,
                    topic_name=topic_label,
                    source_page_number=page_num,
                    supporting_excerpt=excerpt,
                    provenance="extracted",
                    confidence=0.88,
                )
            )
            concepts.append(
                ExtractedConceptItem(
                    title=(excerpt[:60].rstrip(".") or "Core Concept"),
                    explanation=f"Concept derived from source material: {excerpt}",
                    topic_name=topic_label,
                    difficulty="medium",
                    source_page_number=page_num,
                    supporting_excerpt=excerpt,
                    provenance="paraphrased",
                    confidence=0.84,
                )
            )

        # Detect simple MCQ pattern in chunk if present
        mcq_match = re.search(
            r"(?:Q\.?\s*\d+[:.)]?\s*)(.+?)\s*\(A\)\s*(.+?)\s*\(B\)\s*(.+?)"
            r"\s*\(C\)\s*(.+?)\s*\(D\)\s*([^\n]+?)"
            r"(?:\s*(?:\n\s*)?Answer[:\s]+([A-D]))?(?:\n|$)",
            chunk_text,
            re.DOTALL | re.IGNORECASE,
        )
        if mcq_match:
            stem = " ".join(mcq_match.group(1).split())
            ans = mcq_match.group(6).upper() if mcq_match.group(6) else None
            questions.append(
                ExtractedQuestionItem(
                    question_text=stem,
                    question_type="single_choice",
                    subject_code=subject,  # type: ignore[arg-type]
                    topic_name=topic_label,
                    difficulty="medium",
                    options=[
                        ExtractedOptionItem(key="A", text=" ".join(mcq_match.group(2).split())),
                        ExtractedOptionItem(key="B", text=" ".join(mcq_match.group(3).split())),
                        ExtractedOptionItem(key="C", text=" ".join(mcq_match.group(4).split())),
                        ExtractedOptionItem(key="D", text=" ".join(mcq_match.group(5).split())),
                    ],
                    correct_option_key=ans,
                    explanation="",
                    source_page_number=page_num,
                    supporting_excerpt=stem[:240],
                    answer_key_provenance="source_answer_key" if ans else "unverified",
                )
            )

        return json.dumps(
            ChunkExtractionOutput(
                detected_subject_code=subject,  # type: ignore[arg-type]
                topic_names=[f.topic_name for f in facts if f.topic_name],
                facts=facts,
                concepts=concepts,
                questions=questions,
            ).model_dump()
        )

    def _default_notes(self, prompt: str, prompt_name: str) -> str:
        records_match = re.search(r"Stored knowledge records:\n(.*)", prompt, re.DOTALL)
        records: dict[str, Any] = {}
        if records_match:
            try:
                records = json.loads(records_match.group(1).strip())
            except Exception:
                records = {}

        topic_match = re.search(r"for topic '([^']+)'", prompt)
        subj_match = re.search(r"\(subject:\s*([^)]+)\)", prompt)
        topic_name = topic_match.group(1) if topic_match else "Study Topic"
        subject_code = subj_match.group(1).strip() if subj_match else "unknown"

        facts: list[dict[str, Any]] = records.get("facts") or []
        concepts: list[dict[str, Any]] = records.get("concepts") or []
        questions: list[dict[str, Any]] = records.get("questions") or []

        first_ref = []
        if facts:
            f0 = facts[0]
            if f0.get("source_page_number") is not None:
                excerpt_text = str(f0.get("supporting_excerpt") or f0.get("content", ""))
                first_ref = [
                    GeneratedSourceRefItem(
                        page_number=f0.get("source_page_number"),
                        supporting_excerpt=excerpt_text[:200],
                    )
                ]
        elif concepts:
            c0 = concepts[0]
            refs = c0.get("source_refs") or []
            if refs and isinstance(refs[0], dict) and refs[0].get("page_number") is not None:
                first_ref = [
                    GeneratedSourceRefItem(
                        page_number=refs[0].get("page_number"),
                        supporting_excerpt=str(refs[0].get("supporting_excerpt") or "")[:200],
                    )
                ]

        fact_blocks = [
            GeneratedNoteBlock(
                block_type="formula" if f.get("fact_type") == "formula" else "definition",
                title=f"Key {str(f.get('fact_type', 'fact')).title()}",
                body=str(f.get("content", "")),
                provenance="extracted",
                source_refs=(
                    [
                        GeneratedSourceRefItem(
                            page_number=f.get("source_page_number"),
                            supporting_excerpt=str(
                                f.get("supporting_excerpt") or f.get("content", "")
                            )[:200],
                        )
                    ]
                    if f.get("source_page_number") is not None
                    else []
                ),
                review_status="verified",
            )
            for f in facts[:6]
        ]

        concept_blocks = [
            GeneratedNoteBlock(
                block_type="concept",
                title=str(c.get("title", "Core Concept")),
                body=str(c.get("explanation", "")),
                provenance="paraphrased",
                source_refs=first_ref,
                review_status="verified",
            )
            for c in concepts[:4]
        ]

        if "quick_revision" in prompt_name:
            compact_body = "; ".join(str(f.get("content", "")) for f in facts[:3]) or (
                concepts[0].get("explanation", "") if concepts else f"Core points for {topic_name}."
            )
            return GeneratedNoteOutput(
                title=f"{topic_name} — Quick Revision",
                summary=f"Compact revision sheet for {topic_name}.",
                sections=[
                    GeneratedNoteSection(
                        key="key_facts",
                        title="Key Facts & Formulas",
                        blocks=[
                            GeneratedNoteBlock(
                                block_type="recap",
                                title="Must-Know Points",
                                body=compact_body[:260],
                                provenance="extracted" if first_ref else "ai_explanation",
                                source_refs=first_ref,
                            )
                        ],
                    )
                ],
                one_minute_recap=f"1-min recap: Review core rule(s) of {topic_name}.",
            ).model_dump_json()

        if "formula_sheet" in prompt_name:
            return GeneratedNoteOutput(
                title=f"{topic_name} — Formula & Rule Sheet",
                summary=f"Reference formulas and rules for {topic_name}.",
                sections=[
                    GeneratedNoteSection(
                        key="formulas_and_rules",
                        title="Formulas & Core Rules",
                        blocks=fact_blocks
                        or [
                            GeneratedNoteBlock(
                                block_type="rule",
                                title="Core Reference",
                                body=f"Key principles for {topic_name}.",
                                provenance="ai_explanation",
                            )
                        ],
                    )
                ],
            ).model_dump_json()

        if "strategy_sheet" in prompt_name:
            strategy_sections = self._build_mock_strategy_sections(
                subject_code, topic_name, first_ref
            )
            return GeneratedNoteOutput(
                title=f"{topic_name} — Solving Strategies",
                summary=f"Subject-specialized solving methods for {topic_name}.",
                sections=strategy_sections,
            ).model_dump_json()

        # Detailed or regenerate
        sections = [
            GeneratedNoteSection(
                key="learning_objective",
                title="Learning Objective & Why It Matters",
                blocks=[
                    GeneratedNoteBlock(
                        block_type="concept",
                        title="Learning Objective",
                        body=(
                            f"Master {topic_name} by connecting verified source facts with "
                            "exam-ready problem solving."
                        ),
                        provenance="ai_explanation",
                    )
                ],
            ),
            GeneratedNoteSection(
                key="core_concepts",
                title="Core Concept & Step-by-Step Explanation",
                blocks=concept_blocks
                or [
                    GeneratedNoteBlock(
                        block_type="step",
                        title="Step-by-Step Overview",
                        body=f"Detailed walkthrough of {topic_name} based on stored records.",
                        provenance="ai_explanation",
                    )
                ],
            ),
            GeneratedNoteSection(
                key="key_facts",
                title="Important Facts, Formulas & Rules",
                blocks=fact_blocks
                or [
                    GeneratedNoteBlock(
                        block_type="definition",
                        title="Primary Principle",
                        body=f"Foundational definition for {topic_name}.",
                        provenance="ai_explanation",
                    )
                ],
            ),
            GeneratedNoteSection(
                key="misconceptions",
                title="Common Misconceptions & Traps",
                blocks=[
                    GeneratedNoteBlock(
                        block_type="misconception",
                        title="Watch Out For",
                        body=(
                            f"Verify units, conditions, and wording carefully on {topic_name} "
                            "questions before selecting an option."
                        ),
                        provenance="ai_explanation",
                    )
                ],
            ),
        ]
        if questions:
            q0 = questions[0]
            sections.append(
                GeneratedNoteSection(
                    key="representative_questions",
                    title="Representative Questions & Exam Relevance",
                    blocks=[
                        GeneratedNoteBlock(
                            block_type="worked_example",
                            title="Sample Source Question",
                            body=str(q0.get("question_text", "")),
                            provenance="extracted",
                            source_refs=(
                                [
                                    GeneratedSourceRefItem(
                                        page_number=q0.get("source_page_number"),
                                        supporting_excerpt=str(q0.get("question_text", ""))[:180],
                                    )
                                ]
                                if q0.get("source_page_number") is not None
                                else []
                            ),
                        )
                    ],
                )
            )
        return GeneratedNoteOutput(
            title=f"{topic_name} — Detailed Smart Notes",
            summary=f"Comprehensive source-grounded smart notes for {topic_name}.",
            sections=sections,
        ).model_dump_json()

    @staticmethod
    def _build_mock_strategy_sections(
        subject_code: str,
        topic_name: str,
        first_ref: list[GeneratedSourceRefItem],
    ) -> list[GeneratedNoteSection]:
        if subject_code == "quantitative_aptitude":
            return [
                GeneratedNoteSection(
                    key="standard_method",
                    title="Standard & Alternative Methods",
                    blocks=[
                        GeneratedNoteBlock(
                            block_type="strategy",
                            title="Standard Approach",
                            body=(
                                f"Set up exact equations for {topic_name}. "
                                "Example: 250 - 200 = 50."
                            ),
                            provenance="ai_explanation",
                            source_refs=first_ref,
                        )
                    ],
                ),
                GeneratedNoteSection(
                    key="shortcut_method",
                    title="Mathematically Justified Shortcut",
                    blocks=[
                        GeneratedNoteBlock(
                            block_type="strategy",
                            title="Ratio Shortcut",
                            body=(
                                "Use fraction equivalents (e.g. 25% of 200 = 50). "
                                "Estimated time saving: ~15s."
                            ),
                            metadata_items=[
                                NoteBlockMetadataItem(
                                    key="when_safe_to_use",
                                    value=(
                                        "Valid when base value is non-zero and percentages "
                                        "are constant."
                                    ),
                                ),
                                NoteBlockMetadataItem(
                                    key="time_comparison_estimate",
                                    value="Estimated ~20s vs ~35s standard",
                                ),
                            ],
                            provenance="ai_explanation",
                        )
                    ],
                ),
            ]
        if subject_code == "reasoning":
            return [
                GeneratedNoteSection(
                    key="pattern_relationship",
                    title="Pattern & Solving Procedure",
                    blocks=[
                        GeneratedNoteBlock(
                            block_type="strategy",
                            title="Pattern Recognition Cues",
                            body=(
                                f"Identify the structural rule in {topic_name} "
                                "before testing options."
                            ),
                            metadata_items=[
                                NoteBlockMetadataItem(
                                    key="shortcut_failure_cases",
                                    value=(
                                        "Do not apply shortcuts when negative statements or "
                                        "'only a few' appear."
                                    ),
                                )
                            ],
                            provenance="ai_explanation",
                        )
                    ],
                )
            ]
        if subject_code == "english":
            return [
                GeneratedNoteSection(
                    key="grammar_rules",
                    title="Grammar Rules & Elimination",
                    blocks=[
                        GeneratedNoteBlock(
                            block_type="rule",
                            title="Exact Rule & Examples",
                            body=(
                                f"Apply {topic_name} rules strictly; compare correct "
                                "vs. incorrect phrasing."
                            ),
                            metadata_items=[
                                NoteBlockMetadataItem(
                                    key="correct_example",
                                    value="Each of the students has submitted the form.",
                                ),
                                NoteBlockMetadataItem(
                                    key="incorrect_example",
                                    value="Each of the students have submitted the form.",
                                ),
                            ],
                            provenance="ai_explanation",
                        )
                    ],
                )
            ]
        if subject_code == "general_awareness":
            return [
                GeneratedNoteSection(
                    key="five_ws_breakdown",
                    title="5Ws & Static vs Current Breakdown",
                    blocks=[
                        GeneratedNoteBlock(
                            block_type="strategy",
                            title="Structured Fact Table",
                            body=(
                                f"Organize {topic_name} by Who, What, When, Where, Why "
                                "and verify current facts."
                            ),
                            provenance="ai_explanation",
                            source_refs=first_ref,
                        )
                    ],
                )
            ]
        return [
            GeneratedNoteSection(
                key="core_strategy",
                title="Solving Strategy",
                blocks=[
                    GeneratedNoteBlock(
                        block_type="strategy",
                        title="Step-by-Step Method",
                        body=f"Follow verified concepts and check edge cases for {topic_name}.",
                        provenance="ai_explanation",
                    )
                ],
            )
        ]
