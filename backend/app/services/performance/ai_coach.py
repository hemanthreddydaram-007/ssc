from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from app.ai.provider import AIConfigurationError, AIProviderError, LLMProvider
from app.models.assessment import Attempt
from app.schemas.performance import (
    AICoachingLLMOutput,
    AICoachingSummaryOut,
    AICoachingTopicExplanation,
    RuleRecommendationOut,
)

COACHING_PROMPT_NAME = "performance_coaching"
COACHING_PROMPT_VERSION = "v1"

_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_OVERCLAIM_RE = re.compile(
    r"\b(?:you are careless|definitely careless|guaranteed|proven learning disability)\b",
    re.IGNORECASE,
)


def _normalize_numeric_token(raw: str) -> str:
    try:
        d = Decimal(raw)
        if d == d.to_integral_value():
            return str(int(d))
        return format(d.normalize(), "f")
    except Exception:
        return raw


def _collect_allowed_numbers(
    *, attempt: Attempt, recommendations: list[RuleRecommendationOut]
) -> set[str]:
    allowed: set[str] = {
        "5",
        "10",
        "20",
        "35",
        "50",
        "75",
        str(attempt.correct_count),
        str(attempt.incorrect_count),
        str(attempt.skipped_count),
        str(attempt.timed_out_count),
    }
    if attempt.total_score is not None:
        allowed.add(_normalize_numeric_token(str(attempt.total_score)))
    if attempt.max_score is not None:
        allowed.add(_normalize_numeric_token(str(attempt.max_score)))

    def _walk(val: Any) -> None:
        if isinstance(val, bool):
            return
        if isinstance(val, (int, float, Decimal)):
            allowed.add(_normalize_numeric_token(str(val)))
            if isinstance(val, float):
                allowed.add(_normalize_numeric_token(str(round(val, 1))))
                allowed.add(_normalize_numeric_token(str(round(val))))
        elif isinstance(val, str):
            for tok in _NUMBER_RE.findall(val):
                allowed.add(_normalize_numeric_token(tok))
        elif isinstance(val, dict):
            for k, v in val.items():
                _walk(v)
                if k == "average_time_ms" and isinstance(v, (int, float)):
                    secs = round(float(v) / 1000.0, 1)
                    allowed.add(_normalize_numeric_token(str(secs)))
                    allowed.add(str(round(secs)))
        elif isinstance(val, list):
            for item in val:
                _walk(item)

    for rec in recommendations:
        _walk(rec.cited_metrics)
        _walk(rec.observation)
        _walk(rec.recommendation)

    return allowed


def verify_coaching_grounding(
    *,
    output: AICoachingLLMOutput,
    attempt: Attempt,
    recommendations: list[RuleRecommendationOut],
) -> tuple[bool, str | None]:
    """Ensure LLM coaching introduces zero ungrounded numbers or diagnostic overclaims."""
    if not output.summary_text.strip():
        return False, "empty_summary"

    combined_texts = [output.summary_text] + [e.explanation for e in output.topic_explanations]
    full_text = " ".join(combined_texts)

    if _OVERCLAIM_RE.search(full_text):
        return False, "diagnostic_overclaim"

    allowed = _collect_allowed_numbers(attempt=attempt, recommendations=recommendations)
    for tok in _NUMBER_RE.findall(full_text):
        norm = _normalize_numeric_token(tok)
        if norm not in allowed:
            return False, f"ungrounded_number:{tok}"

    return True, None


def build_deterministic_coaching(
    *,
    attempt: Attempt,
    recommendations: list[RuleRecommendationOut],
    status: str = "fallback",
) -> AICoachingSummaryOut:
    """Build plain-language coaching strictly from deterministic rule outputs."""
    attempted = attempt.correct_count + attempt.incorrect_count
    if not recommendations:
        summary = (
            f"You completed {attempted} question(s) with {attempt.correct_count} correct, "
            f"{attempt.incorrect_count} incorrect, {attempt.skipped_count} skipped, and "
            f"{attempt.timed_out_count} timed out. No urgent rule triggers were observed."
        )
    else:
        top = recommendations[:3]
        highlights = " ".join(f"{r.observation} {r.recommendation}" for r in top)
        summary = (
            f"Summary across {attempt.correct_count} correct and {attempt.incorrect_count} "
            f"incorrect answer(s) ({attempt.timed_out_count} timed out): {highlights}"
        )

    topic_explanations: list[AICoachingTopicExplanation] = []
    for rec in recommendations:
        if rec.topic_name:
            topic_explanations.append(
                AICoachingTopicExplanation(
                    topic_name=rec.topic_name,
                    explanation=(
                        f"{rec.observation} {rec.possible_interpretation} {rec.recommendation}"
                    ),
                )
            )

    return AICoachingSummaryOut(
        status=status,  # type: ignore[arg-type]
        summary_text=summary,
        topic_explanations=topic_explanations,
        model_name=None,
        prompt_version=None,
        grounded_only=True,
    )


class AICoachService:
    """Optional plain-language coaching wrapper strictly grounded in deterministic metrics."""

    def generate_coaching(
        self,
        *,
        attempt: Attempt,
        recommendations: list[RuleRecommendationOut],
        include_ai_coaching: bool,
        llm_provider: LLMProvider | None,
    ) -> tuple[AICoachingSummaryOut, str | None]:
        if not include_ai_coaching:
            return (
                build_deterministic_coaching(
                    attempt=attempt,
                    recommendations=recommendations,
                    status="not_requested",
                ),
                None,
            )

        if llm_provider is None:
            return (
                build_deterministic_coaching(
                    attempt=attempt,
                    recommendations=recommendations,
                    status="fallback",
                ),
                None,
            )

        payload_for_llm = {
            "attempt_counts": {
                "correct": attempt.correct_count,
                "incorrect": attempt.incorrect_count,
                "skipped": attempt.skipped_count,
                "timed_out": attempt.timed_out_count,
                "total_score": str(attempt.total_score) if attempt.total_score is not None else "0",
                "max_score": str(attempt.max_score),
            },
            "recommendations": [
                {
                    "rule_id": r.rule_id,
                    "topic_name": r.topic_name,
                    "action_type": r.action_type,
                    "cited_metrics": r.cited_metrics,
                    "observation": r.observation,
                    "possible_interpretation": r.possible_interpretation,
                    "recommendation": r.recommendation,
                }
                for r in recommendations
            ],
        }
        system_instruction = (
            "You are a concise exam study coach. Explain ONLY the metrics and rule-based "
            "recommendations provided in JSON. Never invent numbers, percentages, or causes. "
            "Always distinguish observed metrics from tentative possible interpretations."
        )
        prompt = (
            "Convert these deterministic performance metrics and recommendations into clear, "
            "encouraging student-facing coaching. Cite only numbers present in the JSON.\n\n"
            f"{json.dumps(payload_for_llm, ensure_ascii=True)}"
        )

        try:
            result = llm_provider.generate_structured_output(
                AICoachingLLMOutput,
                prompt,
                system_instruction=system_instruction,
                model_tier="fast",
                temperature=0.1,
                prompt_name=COACHING_PROMPT_NAME,
                prompt_version=COACHING_PROMPT_VERSION,
            )
        except (AIConfigurationError, AIProviderError):
            return (
                build_deterministic_coaching(
                    attempt=attempt,
                    recommendations=recommendations,
                    status="fallback",
                ),
                COACHING_PROMPT_NAME,
            )

        if result.parsed is None or result.status == "failed_validation":
            return (
                build_deterministic_coaching(
                    attempt=attempt,
                    recommendations=recommendations,
                    status="fallback",
                ),
                COACHING_PROMPT_NAME,
            )

        is_grounded, _reason = verify_coaching_grounding(
            output=result.parsed,
            attempt=attempt,
            recommendations=recommendations,
        )
        if not is_grounded:
            return (
                build_deterministic_coaching(
                    attempt=attempt,
                    recommendations=recommendations,
                    status="fallback",
                ),
                COACHING_PROMPT_NAME,
            )

        return (
            AICoachingSummaryOut(
                status="generated",
                summary_text=result.parsed.summary_text.strip(),
                topic_explanations=result.parsed.topic_explanations,
                model_name=result.model_name,
                prompt_version=result.prompt_version,
                grounded_only=True,
            ),
            result.prompt_name,
        )
