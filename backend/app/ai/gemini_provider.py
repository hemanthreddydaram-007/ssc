from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from app.ai.provider import (
    AIConfigurationError,
    AIProviderError,
    BaseLLMProvider,
    BinaryPart,
    ModelTier,
    TextPart,
    _RawProviderResponse,
)
from app.core.config import Settings

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text_for_llm(text: str) -> str:
    """Strip lone UTF-16 surrogates and non-whitespace control characters from text."""
    if not text:
        return ""
    utf8_safe = text.encode("utf-8", errors="replace").decode("utf-8")
    return _CONTROL_CHARS_RE.sub("", utf8_safe)


def _clean_api_key(raw: str) -> str:
    cleaned = raw.strip()
    if len(cleaned) >= 2 and (
        (cleaned[0] == '"' and cleaned[-1] == '"')
        or (cleaned[0] == "'" and cleaned[-1] == "'")
    ):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _format_api_error(exc: genai_errors.APIError) -> str:
    raw = getattr(exc, "message", None)
    if not raw:
        details = getattr(exc, "details", None)
        if isinstance(details, dict):
            err_obj = details.get("error")
            if isinstance(err_obj, dict):
                raw = err_obj.get("message")
        raw = raw or str(exc)
    collapsed = " ".join(str(raw).splitlines()).strip()
    return collapsed[:400]


def _is_auth_or_config_400(err_msg: str) -> bool:
    lowered = err_msg.lower()
    return any(
        token in lowered
        for token in (
            "api key",
            "api_key",
            "permission",
            "billing",
            "quota",
            "user location",
            "location is not supported",
        )
    )


def _is_daily_quota_429(err_msg: str) -> bool:
    lowered = err_msg.lower()
    return any(
        token in lowered
        for token in (
            "requestsperday",
            "perday",
            "free_tier_requests",
            "exceeded your current quota",
        )
    )


class GeminiLLMProvider(BaseLLMProvider):
    """Google GenAI SDK adapter with multi-key rotation and model fallback on 429 quota."""

    def __init__(
        self,
        settings: Settings,
        *,
        api_key_override: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 1.0,
    ) -> None:
        self.settings = settings
        self.api_key_override = api_key_override
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self._clients: dict[str, genai.Client] = {}

    def _resolve_model(self, model_tier: ModelTier) -> str:
        if model_tier == "fast":
            return self.settings.gemini_model_fast
        if model_tier == "vision":
            return self.settings.gemini_model_vision
        return self.settings.gemini_model_standard

    def _candidate_models(self, model_tier: ModelTier) -> list[str]:
        primary = self._resolve_model(model_tier).strip()
        fallbacks_raw = getattr(self.settings, "gemini_fallback_models", "") or ""
        candidates: list[str] = []
        if primary:
            candidates.append(primary)
        for item in fallbacks_raw.split(","):
            cleaned = item.strip()
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
        return candidates

    def _candidate_api_keys(self) -> list[str]:
        keys: list[str] = []
        if self.api_key_override:
            cleaned_override = _clean_api_key(self.api_key_override)
            if cleaned_override:
                keys.append(cleaned_override)
        secret = self.settings.gemini_api_key
        if secret is not None:
            cleaned_primary = _clean_api_key(secret.get_secret_value())
            if cleaned_primary and cleaned_primary not in keys:
                keys.append(cleaned_primary)
        pool_raw = getattr(self.settings, "gemini_api_keys", "") or ""
        for item in pool_raw.split(","):
            cleaned = _clean_api_key(item)
            if cleaned and cleaned not in keys:
                keys.append(cleaned)
        if not keys:
            raise AIConfigurationError(
                "GEMINI_API_KEY is not configured; live Gemini generation is unavailable."
            )
        return keys

    def _get_client_for_key(self, api_key: str) -> genai.Client:
        existing = self._clients.get(api_key)
        if existing is not None:
            return existing
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1beta"),
        )
        self._clients[api_key] = client
        return client

    @staticmethod
    def _to_contents(prompt: str, context_parts: Sequence[Any]) -> list[Any]:
        cleaned_prompt = sanitize_text_for_llm(prompt) or "Respond with valid JSON."
        contents: list[Any] = [cleaned_prompt]
        for part in context_parts:
            if isinstance(part, str):
                cleaned = sanitize_text_for_llm(part)
                if cleaned:
                    contents.append(cleaned)
            elif isinstance(part, TextPart):
                cleaned = sanitize_text_for_llm(part.text)
                if cleaned:
                    contents.append(cleaned)
            elif isinstance(part, BinaryPart):
                contents.append(types.Part.from_bytes(data=part.data, mime_type=part.mime_type))
            else:
                cleaned = sanitize_text_for_llm(str(part))
                if cleaned:
                    contents.append(cleaned)
        return contents

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, int]:
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return {}
        usage: dict[str, int] = {}
        for src, dst in (
            ("prompt_token_count", "input_tokens"),
            ("candidates_token_count", "output_tokens"),
            ("total_token_count", "total_tokens"),
        ):
            val = getattr(meta, src, None)
            if isinstance(val, int):
                usage[dst] = val
        return usage

    def _call_single_target(
        self,
        *,
        client: genai.Client,
        model_name: str,
        contents: list[Any],
        config: types.GenerateContentConfig,
        prompt_name: str,
        prompt_version: str,
        has_failover: bool,
    ) -> Any:
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except genai_errors.APIError as exc:
                last_exc = exc
                status_code = getattr(exc, "code", None)
                err_msg = _format_api_error(exc)
                logger.error(
                    "Gemini API error (status=%s model=%s prompt=%s version=%s): %s",
                    status_code,
                    model_name,
                    prompt_name,
                    prompt_version,
                    err_msg,
                )
                # Daily quota exhaustion cannot be resolved by retrying the same key+model
                if status_code == 429 and (_is_daily_quota_429(err_msg) or has_failover):
                    raise AIProviderError(
                        f"Gemini API error ({status_code}) on "
                        f"{prompt_name}:{prompt_version}: {err_msg}"
                    ) from exc
                if status_code not in _TRANSIENT_STATUS_CODES or attempt >= self.max_retries:
                    raise AIProviderError(
                        f"Gemini API error ({status_code}) on "
                        f"{prompt_name}:{prompt_version}: {err_msg}"
                    ) from exc
            except (TimeoutError, ConnectionError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise AIProviderError(
                        f"Gemini transport error on {prompt_name}:{prompt_version}"
                    ) from exc

            delay = self.backoff_base_seconds * (2**attempt) + random.uniform(0.0, 0.25)
            if (
                isinstance(last_exc, genai_errors.APIError)
                and getattr(last_exc, "code", None) == 429
                and self.backoff_base_seconds > 0
            ):
                delay = max(delay, min(8.0, self.backoff_base_seconds * 4 * (attempt + 1)))
            logger.warning(
                "Retrying transient Gemini call (model=%s prompt=%s version=%s attempt=%s)",
                model_name,
                prompt_name,
                prompt_version,
                attempt + 1,
            )
            time.sleep(delay)

        raise AIProviderError(
            f"Gemini call failed after retries on {prompt_name}:{prompt_version}"
        ) from last_exc

    def _call_with_failover(
        self,
        *,
        model_tier: ModelTier,
        contents: list[Any],
        config: types.GenerateContentConfig,
        prompt_name: str,
        prompt_version: str,
    ) -> tuple[Any, str]:
        api_keys = self._candidate_api_keys()
        models = self._candidate_models(model_tier)
        targets = [(key, model) for key in api_keys for model in models]
        last_error: AIProviderError | None = None

        for idx, (api_key, model_name) in enumerate(targets):
            has_failover = idx < len(targets) - 1
            client = self._get_client_for_key(api_key)
            try:
                response = self._call_single_target(
                    client=client,
                    model_name=model_name,
                    contents=contents,
                    config=config,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    has_failover=has_failover,
                )
                return response, model_name
            except AIProviderError as exc:
                last_error = exc
                cause = exc.__cause__
                status_code = getattr(cause, "code", None)
                # Failover across models/keys ONLY on 429 quota or 404 unsupported fallback model.
                can_failover = status_code == 429 or (status_code == 404 and has_failover)
                if not can_failover or not has_failover:
                    raise
                logger.warning(
                    "Failing over Gemini call from model=%s after status=%s (%s:%s)",
                    model_name,
                    status_code,
                    prompt_name,
                    prompt_version,
                )

        assert last_error is not None
        raise last_error

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
        clean_system = (
            sanitize_text_for_llm(system_instruction) if system_instruction is not None else None
        )
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=clean_system,
            response_mime_type="application/json",
            response_schema=schema,
            http_options=types.HttpOptions(
                api_version="v1beta",
                timeout=int(self.timeout_seconds * 1000),
            ),
        )
        contents = self._to_contents(prompt, context_parts)
        try:
            response, used_model = self._call_with_failover(
                model_tier=model_tier,
                contents=contents,
                config=config,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
            )
        except AIProviderError as exc:
            cause = exc.__cause__
            if (
                isinstance(cause, genai_errors.APIError)
                and getattr(cause, "code", None) == 400
                and not _is_auth_or_config_400(_format_api_error(cause))
            ):
                logger.warning(
                    "Gemini rejected response_schema with 400 on %s:%s; retrying in JSON mode "
                    "with inline schema validation.",
                    prompt_name,
                    prompt_version,
                )
                schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=True)
                fallback_contents = list(contents)
                fallback_contents[0] = (
                    f"{contents[0]}\n\nReturn ONLY valid JSON matching this JSON schema:\n"
                    f"{schema_hint}"
                )
                fallback_config = types.GenerateContentConfig(
                    temperature=temperature,
                    system_instruction=clean_system,
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(
                        api_version="v1beta",
                        timeout=int(self.timeout_seconds * 1000),
                    ),
                )
                response, used_model = self._call_with_failover(
                    model_tier=model_tier,
                    contents=fallback_contents,
                    config=fallback_config,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                )
            else:
                raise
        raw_text = getattr(response, "text", None) or ""
        return _RawProviderResponse(
            raw_text=raw_text,
            model_name=used_model,
            token_usage=self._extract_usage(response),
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
        clean_system = (
            sanitize_text_for_llm(system_instruction) if system_instruction is not None else None
        )
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=clean_system,
            http_options=types.HttpOptions(
                api_version="v1beta",
                timeout=int(self.timeout_seconds * 1000),
            ),
        )
        contents: list[Any] = [sanitize_text_for_llm(prompt) or "Respond concisely."]
        if context:
            cleaned_context = sanitize_text_for_llm(context)
            if cleaned_context:
                contents.append(cleaned_context)
        response, used_model = self._call_with_failover(
            model_tier=model_tier,
            contents=contents,
            config=config,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        raw_text = getattr(response, "text", None) or ""
        return _RawProviderResponse(
            raw_text=raw_text,
            model_name=used_model,
            token_usage=self._extract_usage(response),
        )
