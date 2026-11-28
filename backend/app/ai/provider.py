from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, Protocol, TypeVar, runtime_checkable

from fastapi import Depends, Header
from pydantic import BaseModel, ValidationError

from app.ai.prompts.extraction import QUESTION_VERIFICATION_PROMPT_V1
from app.ai.schemas.common import QuestionVerificationResult
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

ModelTier = Literal["fast", "standard", "vision"]
ValidationStatus = Literal["valid", "repaired", "failed_validation"]


class AIConfigurationError(RuntimeError):
    """Raised when live AI provider credentials or model settings are missing."""


class AIProviderError(RuntimeError):
    """Raised when an upstream AI provider call fails after configured retries."""


@dataclass(frozen=True, slots=True)
class TextPart:
    """Provider-neutral text context part."""

    text: str


@dataclass(frozen=True, slots=True)
class BinaryPart:
    """Provider-neutral binary attachment (image or PDF bytes)."""

    data: bytes
    mime_type: str


ContentPart = str | TextPart | BinaryPart


@dataclass(slots=True)
class LLMResult(Generic[T]):
    """Envelope returned by structured LLM calls with provenance and validation telemetry."""

    parsed: T | None
    raw_text: str
    model_name: str
    prompt_name: str
    prompt_version: str
    token_usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    validation_attempts: int = 1
    status: ValidationStatus = "valid"
    error_message: str | None = None


@dataclass(slots=True)
class LLMTextResult:
    """Envelope returned by free-text LLM calls."""

    text: str
    model_name: str
    prompt_name: str
    prompt_version: str
    token_usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    error_message: str | None = None


@dataclass(slots=True)
class _RawProviderResponse:
    raw_text: str
    model_name: str
    token_usage: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-agnostic interface isolating LLM SDKs from domain services."""

    def generate_structured_output(
        self,
        schema: type[T],
        prompt: str,
        *,
        context_parts: Sequence[Any] = (),
        system_instruction: str | None = None,
        model_tier: ModelTier = "standard",
        temperature: float = 0.1,
        prompt_name: str = "unnamed",
        prompt_version: str = "v1",
    ) -> LLMResult[T]: ...

    def generate_text(
        self,
        prompt: str,
        *,
        context: str | None = None,
        system_instruction: str | None = None,
        model_tier: ModelTier = "fast",
        temperature: float = 0.3,
        prompt_name: str = "unnamed",
        prompt_version: str = "v1",
    ) -> LLMTextResult: ...

    def verify_question(
        self,
        question_payload: dict[str, Any],
        evidence: Sequence[Any] = (),
        *,
        model_tier: ModelTier = "standard",
        prompt_name: str = "question_verify",
        prompt_version: str = "v1",
    ) -> LLMResult[QuestionVerificationResult]: ...


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)


def _strip_json_fences(raw_text: str) -> str:
    stripped = raw_text.strip()
    match = _JSON_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _merge_token_usage(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    keys = set(a) | set(b)
    return {k: int(a.get(k, 0)) + int(b.get(k, 0)) for k in keys}


def _build_repair_prompt(
    *,
    schema: type[BaseModel],
    malformed_output: str,
    validation_error: str,
) -> str:
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=True)
    return (
        "Your previous response failed JSON/Pydantic schema validation. "
        "Return ONLY valid JSON matching the exact schema below.\n\n"
        f"Validation error:\n{validation_error}\n\n"
        f"Target JSON schema:\n{schema_json}\n\n"
        f"Malformed output to repair:\n{malformed_output[:4000]}"
    )


class BaseLLMProvider(ABC):
    """Shared Pydantic validation + single-retry repair orchestration for LLM providers."""

    @abstractmethod
    def _invoke_structured(
        self,
        schema: type[T],
        prompt: str,
        *,
        context_parts: Sequence[Any],
        system_instruction: str | None,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str,
        prompt_version: str,
    ) -> _RawProviderResponse:
        """Execute a single structured generation call against the concrete provider."""

    @abstractmethod
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
        """Execute a single text generation call against the concrete provider."""

    def generate_structured_output(
        self,
        schema: type[T],
        prompt: str,
        *,
        context_parts: Sequence[Any] = (),
        system_instruction: str | None = None,
        model_tier: ModelTier = "standard",
        temperature: float = 0.1,
        prompt_name: str = "unnamed",
        prompt_version: str = "v1",
    ) -> LLMResult[T]:
        started = time.perf_counter()
        raw_resp = self._invoke_structured(
            schema,
            prompt,
            context_parts=context_parts,
            system_instruction=system_instruction,
            model_tier=model_tier,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        total_usage = dict(raw_resp.token_usage)

        try:
            parsed = schema.model_validate_json(_strip_json_fences(raw_resp.raw_text))
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "LLM structured output valid",
                extra={
                    "prompt_name": prompt_name,
                    "prompt_version": prompt_version,
                    "model_name": raw_resp.model_name,
                    "status": "valid",
                    "latency_ms": latency_ms,
                },
            )
            return LLMResult(
                parsed=parsed,
                raw_text=raw_resp.raw_text,
                model_name=raw_resp.model_name,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                token_usage=total_usage,
                latency_ms=latency_ms,
                validation_attempts=1,
                status="valid",
            )
        except (ValidationError, ValueError) as first_err:
            repair_prompt = _build_repair_prompt(
                schema=schema,
                malformed_output=raw_resp.raw_text,
                validation_error=str(first_err),
            )
            repair_resp = self._invoke_structured(
                schema,
                repair_prompt,
                context_parts=(),
                system_instruction=system_instruction,
                model_tier=model_tier,
                temperature=0.0,
                prompt_name=f"{prompt_name}:repair",
                prompt_version=prompt_version,
            )
            total_usage = _merge_token_usage(total_usage, repair_resp.token_usage)
            latency_ms = int((time.perf_counter() - started) * 1000)

            try:
                repaired_parsed = schema.model_validate_json(
                    _strip_json_fences(repair_resp.raw_text)
                )
                logger.info(
                    "LLM structured output repaired",
                    extra={
                        "prompt_name": prompt_name,
                        "prompt_version": prompt_version,
                        "model_name": repair_resp.model_name,
                        "status": "repaired",
                        "latency_ms": latency_ms,
                    },
                )
                return LLMResult(
                    parsed=repaired_parsed,
                    raw_text=repair_resp.raw_text,
                    model_name=repair_resp.model_name,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    token_usage=total_usage,
                    latency_ms=latency_ms,
                    validation_attempts=2,
                    status="repaired",
                )
            except (ValidationError, ValueError) as second_err:
                logger.warning(
                    "LLM structured output failed validation after repair",
                    extra={
                        "prompt_name": prompt_name,
                        "prompt_version": prompt_version,
                        "model_name": repair_resp.model_name,
                        "status": "failed_validation",
                        "latency_ms": latency_ms,
                    },
                )
                return LLMResult(
                    parsed=None,
                    raw_text=repair_resp.raw_text,
                    model_name=repair_resp.model_name,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    token_usage=total_usage,
                    latency_ms=latency_ms,
                    validation_attempts=2,
                    status="failed_validation",
                    error_message=str(second_err),
                )

    def generate_text(
        self,
        prompt: str,
        *,
        context: str | None = None,
        system_instruction: str | None = None,
        model_tier: ModelTier = "fast",
        temperature: float = 0.3,
        prompt_name: str = "unnamed",
        prompt_version: str = "v1",
    ) -> LLMTextResult:
        started = time.perf_counter()
        resp = self._invoke_text(
            prompt,
            context=context,
            system_instruction=system_instruction,
            model_tier=model_tier,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMTextResult(
            text=resp.raw_text,
            model_name=resp.model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            token_usage=resp.token_usage,
            latency_ms=latency_ms,
        )

    def verify_question(
        self,
        question_payload: dict[str, Any],
        evidence: Sequence[Any] = (),
        *,
        model_tier: ModelTier = "standard",
        prompt_name: str = "question_verify",
        prompt_version: str = "v1",
    ) -> LLMResult[QuestionVerificationResult]:
        evidence_lines: list[str] = []
        passthrough_parts: list[Any] = []
        for item in evidence:
            if isinstance(item, str):
                evidence_lines.append(item)
            elif isinstance(item, TextPart):
                evidence_lines.append(item.text)
            else:
                passthrough_parts.append(item)

        prompt = QUESTION_VERIFICATION_PROMPT_V1.render(
            question_json=json.dumps(question_payload, ensure_ascii=True, default=str),
            evidence_text="\n---\n".join(evidence_lines) or "(none supplied)",
        )
        return self.generate_structured_output(
            QuestionVerificationResult,
            prompt,
            context_parts=passthrough_parts,
            system_instruction=QUESTION_VERIFICATION_PROMPT_V1.system_instruction,
            model_tier=model_tier,
            temperature=0.0,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )


def get_llm_provider(
    settings: Settings = Depends(get_settings),
    x_gemini_api_key: str | None = Header(default=None, alias="X-Gemini-Api-Key"),
) -> LLMProvider:
    """FastAPI dependency returning the configured `LLMProvider` implementation."""
    from app.ai.gemini_provider import GeminiLLMProvider  # noqa: PLC0415

    override = x_gemini_api_key if isinstance(x_gemini_api_key, str) else None
    return GeminiLLMProvider(settings=settings, api_key_override=override)
