from __future__ import annotations

import logging
import random
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


class GeminiLLMProvider(BaseLLMProvider):
    """Google GenAI SDK adapter implementing `LLMProvider`."""

    def __init__(
        self,
        settings: Settings,
        *,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 1.0,
    ) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self._client: genai.Client | None = None

    def _resolve_model(self, model_tier: ModelTier) -> str:
        if model_tier == "fast":
            return self.settings.gemini_model_fast
        if model_tier == "vision":
            return self.settings.gemini_model_vision
        return self.settings.gemini_model_standard

    def _get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        secret = self.settings.gemini_api_key
        api_key = secret.get_secret_value().strip() if secret is not None else ""
        if not api_key:
            raise AIConfigurationError(
                "GEMINI_API_KEY is not configured; live Gemini generation is unavailable."
            )
        self._client = genai.Client(api_key=api_key)
        return self._client

    @staticmethod
    def _to_contents(prompt: str, context_parts: Sequence[Any]) -> list[Any]:
        contents: list[Any] = [prompt]
        for part in context_parts:
            if isinstance(part, str):
                contents.append(part)
            elif isinstance(part, TextPart):
                contents.append(part.text)
            elif isinstance(part, BinaryPart):
                contents.append(types.Part.from_bytes(data=part.data, mime_type=part.mime_type))
            else:
                contents.append(str(part))
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

    def _call_with_backoff(
        self,
        *,
        model_name: str,
        contents: list[Any],
        config: types.GenerateContentConfig,
        prompt_name: str,
        prompt_version: str,
    ) -> Any:
        client = self._get_client()
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
                err_msg = str(getattr(exc, "message", None) or exc).splitlines()[0][:160]
                logger.error(
                    "Gemini API error (status=%s prompt=%s version=%s): %s",
                    status_code,
                    prompt_name,
                    prompt_version,
                    err_msg,
                )
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
            logger.warning(
                "Retrying transient Gemini call (prompt=%s version=%s attempt=%s)",
                prompt_name,
                prompt_version,
                attempt + 1,
            )
            time.sleep(delay)

        raise AIProviderError(
            f"Gemini call failed after retries on {prompt_name}:{prompt_version}"
        ) from last_exc

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
        model_name = self._resolve_model(model_tier)
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
            http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
        )
        contents = self._to_contents(prompt, context_parts)
        response = self._call_with_backoff(
            model_name=model_name,
            contents=contents,
            config=config,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        raw_text = getattr(response, "text", None) or ""
        return _RawProviderResponse(
            raw_text=raw_text,
            model_name=model_name,
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
        model_name = self._resolve_model(model_tier)
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
        )
        contents: list[Any] = [prompt]
        if context:
            contents.append(context)
        response = self._call_with_backoff(
            model_name=model_name,
            contents=contents,
            config=config,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        raw_text = getattr(response, "text", None) or ""
        return _RawProviderResponse(
            raw_text=raw_text,
            model_name=model_name,
            token_usage=self._extract_usage(response),
        )
