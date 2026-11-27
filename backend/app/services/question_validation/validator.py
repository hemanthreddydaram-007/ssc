from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.ai.provider import LLMProvider, TextPart
from app.services.question_validation.math_solver import verify_question_math
from app.services.question_validation.option_checks import check_single_choice_options


@dataclass(slots=True)
class QuestionValidationOutcome:
    """Combined deterministic + optional LLM verification result for a question."""

    validation_status: str
    answer_key_provenance: str
    warnings: list[str] = field(default_factory=list)
    math_checked: bool = False
    llm_verified: bool | None = None


class QuestionValidationService:
    """Validates MCQ options, deterministic math, provenance, and optional LLM verification."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self._llm_provider = llm_provider

    def validate_question(
        self,
        *,
        question_text: str,
        question_type: str,
        subject_code: str,
        options: Sequence[tuple[str, str]],
        correct_option_key: str | None,
        explanation: str = "",
        origin: str = "extracted",
        answer_key_provenance: str = "source_answer_key",
        supporting_excerpt: str | None = None,
        evidence_texts: Sequence[str] = (),
        run_llm_verify: bool = False,
    ) -> QuestionValidationOutcome:
        """Run all deterministic checks and optional LLM verification for a question."""
        warnings: list[str] = []
        provenance = answer_key_provenance or "unverified"
        cleaned_stem = " ".join(question_text.split()).strip()

        if len(cleaned_stem) < 5:
            warnings.append("Question stem is missing or too short to be unambiguous.")

        if question_type == "single_choice":
            opt_res = check_single_choice_options(options, correct_option_key)
            warnings.extend(opt_res.warnings)
            normalized_options = opt_res.normalized_options
            cleaned_key = opt_res.correct_option_key
        else:
            normalized_options = [
                (str(k or "").strip().upper(), " ".join(str(t or "").split()).strip())
                for k, t in options
            ]
            cleaned_key = str(correct_option_key).strip().upper() if correct_option_key else None
            if not cleaned_key:
                warnings.append("Missing correct_option_key.")

        math_res = verify_question_math(
            question_text=cleaned_stem,
            options=normalized_options,
            correct_option_key=cleaned_key,
            explanation=explanation,
        )
        if not math_res.is_consistent:
            warnings.extend(math_res.warnings)
            if math_res.checked and cleaned_key and math_res.matched_option_keys:
                if cleaned_key not in math_res.matched_option_keys:
                    provenance = "conflicting"

        if provenance in ("unverified", "conflicting"):
            warnings.append(f"Answer key provenance is '{provenance}'.")

        if origin == "extracted" and not (supporting_excerpt and supporting_excerpt.strip()):
            warnings.append("Extracted question lacks a supporting_excerpt.")

        # Never auto-verify user-supplied answer keys unless deterministically confirmed.
        if provenance == "user_supplied" and not (math_res.checked and math_res.is_consistent):
            warnings.append(
                "User-supplied answer key has not been deterministically or manually verified."
            )

        if origin == "generated" and not (explanation and explanation.strip()):
            warnings.append("Generated question is missing an explanation.")

        llm_verified: bool | None = None
        if run_llm_verify and self._llm_provider is not None and not warnings:
            payload: dict[str, Any] = {
                "question_text": cleaned_stem,
                "question_type": question_type,
                "subject_code": subject_code,
                "options": [{"key": k, "text": t} for k, t in normalized_options],
                "correct_option_key": cleaned_key,
                "explanation": explanation,
            }
            evidence_parts = [TextPart(text=t) for t in evidence_texts if t and t.strip()]
            verify_result = self._llm_provider.verify_question(payload, evidence=evidence_parts)
            if verify_result.status == "failed_validation" or verify_result.parsed is None:
                llm_verified = False
                warnings.append("LLM verification failed schema validation.")
            else:
                verdict = verify_result.parsed
                if not verdict.is_valid or verdict.confidence < 0.6:
                    llm_verified = False
                    issue_summary = (
                        "; ".join(verdict.issues) if verdict.issues else verdict.reasoning
                    )
                    warnings.append(f"LLM verifier flagged question: {issue_summary}")
                else:
                    llm_verified = True
                    if math_res.checked and math_res.is_consistent:
                        provenance = "deterministic_solver"
                    elif provenance not in ("source_answer_key", "deterministic_solver", "manual"):
                        provenance = "ai_verified"
        elif math_res.checked and math_res.is_consistent and origin == "generated":
            provenance = "deterministic_solver"

        status = "verified" if len(warnings) == 0 else "needs_review"
        return QuestionValidationOutcome(
            validation_status=status,
            answer_key_provenance=provenance,
            warnings=warnings,
            math_checked=math_res.checked,
            llm_verified=llm_verified,
        )
