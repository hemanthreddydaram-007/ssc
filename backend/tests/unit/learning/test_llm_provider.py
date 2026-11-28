from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors as genai_errors
from pydantic import SecretStr

from app.ai.gemini_provider import GeminiLLMProvider, _clean_api_key, sanitize_text_for_llm
from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import AIConfigurationError, AIProviderError, BinaryPart
from app.ai.schemas.classification import DocumentClassificationOutput
from app.ai.schemas.common import QuestionVerificationResult
from app.core.config import Settings


def test_mock_provider_valid_json_succeeds_in_one_attempt() -> None:
    provider = MockLLMProvider()
    provider.enqueue_raw(
        '{"subject_code": "quantitative_aptitude", "material_type": "notes", '
        '"language": "en", "confidence": 0.92, "topic_candidates": ["Percentages"], '
        '"rationale": "math"}',
        prompt_name="document_classification",
    )

    result = provider.generate_structured_output(
        DocumentClassificationOutput,
        "Classify percentages notes",
        prompt_name="document_classification",
        prompt_version="v1",
    )

    assert result.status == "valid"
    assert result.validation_attempts == 1
    assert result.parsed is not None
    assert result.parsed.subject_code == "quantitative_aptitude"
    assert result.parsed.confidence == 0.92


def test_mock_provider_strips_markdown_code_fences() -> None:
    provider = MockLLMProvider()
    provider.enqueue_raw(
        '```json\n{"subject_code": "english", "material_type": "pyq_paper", '
        '"language": "en", "confidence": 0.85, "topic_candidates": [], "rationale": "ok"}\n```',
        prompt_name="document_classification",
    )

    result = provider.generate_structured_output(
        DocumentClassificationOutput,
        "Classify english PYQ",
        prompt_name="document_classification",
    )

    assert result.status == "valid"
    assert result.parsed is not None
    assert result.parsed.subject_code == "english"


def test_structured_output_runs_single_repair_retry_on_invalid_json() -> None:
    provider = MockLLMProvider()
    provider.enqueue_raw("{not valid json", prompt_name="document_classification")
    provider.enqueue_raw(
        '{"subject_code": "reasoning", "material_type": "question_bank", '
        '"language": "en", "confidence": 0.88, "topic_candidates": ["Syllogism"], '
        '"rationale": "fixed"}',
        prompt_name="document_classification:repair",
    )

    result = provider.generate_structured_output(
        DocumentClassificationOutput,
        "Classify syllogism",
        prompt_name="document_classification",
        prompt_version="v1",
    )

    assert result.status == "repaired"
    assert result.validation_attempts == 2
    assert result.parsed is not None
    assert result.parsed.subject_code == "reasoning"
    assert len(provider.calls) == 2
    assert provider.calls[1]["prompt_name"] == "document_classification:repair"
    assert "Malformed output to repair" in provider.calls[1]["prompt"]


def test_structured_output_double_failure_returns_failed_validation_never_silently_passes() -> None:
    provider = MockLLMProvider()
    provider.enqueue_raw(
        '{"subject_code": "invalid_subject"}', prompt_name="document_classification"
    )
    provider.enqueue_raw("still broken", prompt_name="document_classification:repair")

    result = provider.generate_structured_output(
        DocumentClassificationOutput,
        "Classify unknown",
        prompt_name="document_classification",
    )

    assert result.status == "failed_validation"
    assert result.validation_attempts == 2
    assert result.parsed is None
    assert result.error_message


def test_verify_question_returns_structured_verification_result() -> None:
    provider = MockLLMProvider()
    result = provider.verify_question(
        {"question_text": "What is 10% of 200?", "options": [{"key": "A", "text": "20"}]},
        evidence=["10% of 200 equals 20."],
    )

    assert result.status == "valid"
    assert isinstance(result.parsed, QuestionVerificationResult)
    assert result.parsed.is_valid is True


def test_gemini_provider_raises_configuration_error_when_api_key_missing() -> None:
    settings = Settings(gemini_api_key=None)
    provider = GeminiLLMProvider(settings=settings)

    with pytest.raises(AIConfigurationError, match="GEMINI_API_KEY"):
        provider.generate_structured_output(
            DocumentClassificationOutput,
            "Classify something",
            prompt_name="document_classification",
        )


def test_gemini_provider_calls_sdk_with_schema_and_never_logs_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_value = "super-secret-gemini-key-12345"
    settings = Settings(
        gemini_api_key=SecretStr(secret_value),
        gemini_model_fast="gemini-2.5-flash",
    )
    provider = GeminiLLMProvider(settings=settings, max_retries=0)

    fake_response = SimpleNamespace(
        text=(
            '{"subject_code": "general_awareness", "material_type": "notes", "language": "en", '
            '"confidence": 0.9, "topic_candidates": ["Polity"], "rationale": "ok"}'
        ),
        usage_metadata=SimpleNamespace(
            prompt_token_count=120,
            candidates_token_count=45,
            total_token_count=165,
        ),
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = fake_response

    with (
        caplog.at_level(logging.INFO),
        patch("app.ai.gemini_provider.genai.Client", return_value=mock_client),
    ):
        result = provider.generate_structured_output(
            DocumentClassificationOutput,
            "Article 14 guarantees equality before law.",
            context_parts=[BinaryPart(data=b"imgbytes", mime_type="image/png")],
            model_tier="fast",
            prompt_name="document_classification",
            prompt_version="v1",
        )

    assert result.status == "valid"
    assert result.parsed is not None
    assert result.parsed.subject_code == "general_awareness"
    assert result.token_usage == {"input_tokens": 120, "output_tokens": 45, "total_tokens": 165}
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert call_kwargs["config"].response_mime_type == "application/json"
    assert call_kwargs["config"].response_schema is DocumentClassificationOutput
    assert secret_value not in caplog.text


def test_sanitize_text_for_llm_strips_surrogates_and_control_chars() -> None:
    assert sanitize_text_for_llm("") == ""

    raw = "abc\ud800def\x00\x07\x0b\x0c\x1f\n\t ok\x7f"
    cleaned = sanitize_text_for_llm(raw)
    assert "\ud800" not in cleaned
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "\x0b" not in cleaned
    assert "\x0c" not in cleaned
    assert "\x1f" not in cleaned
    assert "\x7f" not in cleaned
    assert "abc" in cleaned
    assert "def\n\t ok" in cleaned
    cleaned.encode("utf-8")


def test_clean_api_key_strips_whitespace_and_wrapping_quotes() -> None:
    assert _clean_api_key("  'AIza-test-123'  ") == "AIza-test-123"
    assert _clean_api_key('  "AIza-test-456"  ') == "AIza-test-456"
    assert _clean_api_key("   ") == ""


def test_gemini_provider_uses_v1beta_and_falls_back_on_schema_400(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_value = "AIzaSy-secret-key-fallback"
    settings = Settings(
        gemini_api_key=SecretStr(f"  '{secret_value}'  "),
        gemini_model_fast="gemini-2.5-flash",
    )
    provider = GeminiLLMProvider(settings, max_retries=0, backoff_base_seconds=0.0)

    schema_err = genai_errors.APIError(
        400,
        {"error": {"message": "Invalid JSON payload: nesting depth in response_schema"}},
    )
    fallback_response = SimpleNamespace(
        text=(
            '{"subject_code": "reasoning", "material_type": "notes", '
            '"language": "en", "confidence": 0.91, "topic_candidates": ["Syllogism"], '
            '"rationale": "deductive"}'
        ),
        usage_metadata=SimpleNamespace(
            prompt_token_count=90,
            candidates_token_count=30,
            total_token_count=120,
        ),
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [schema_err, fallback_response]

    with (
        caplog.at_level(logging.WARNING),
        patch("app.ai.gemini_provider.genai.Client", return_value=mock_client) as mock_ctor,
    ):
        result = provider.generate_structured_output(
            DocumentClassificationOutput,
            "Classify\ud800 prompt\x00",
            system_instruction="Be\x07 precise",
            model_tier="fast",
            prompt_name="document_classification",
            prompt_version="v1",
        )

    assert result.status == "valid"
    assert result.parsed is not None
    assert result.parsed.subject_code == "reasoning"
    assert result.token_usage == {"input_tokens": 90, "output_tokens": 30, "total_tokens": 120}

    ctor_kwargs = mock_ctor.call_args.kwargs
    assert ctor_kwargs["api_key"] == secret_value
    assert ctor_kwargs["http_options"].api_version == "v1beta"

    assert mock_client.models.generate_content.call_count == 2
    primary_call, fallback_call = mock_client.models.generate_content.call_args_list
    assert primary_call.kwargs["config"].response_schema is DocumentClassificationOutput
    assert primary_call.kwargs["config"].http_options.api_version == "v1beta"
    assert primary_call.kwargs["config"].system_instruction == "Be precise"
    assert "\ud800" not in primary_call.kwargs["contents"][0]
    assert "\x00" not in primary_call.kwargs["contents"][0]

    assert fallback_call.kwargs["config"].response_schema is None
    assert fallback_call.kwargs["config"].response_mime_type == "application/json"
    assert fallback_call.kwargs["config"].http_options.api_version == "v1beta"
    assert (
        "Return ONLY valid JSON matching this JSON schema:"
        in fallback_call.kwargs["contents"][0]
    )
    assert secret_value not in caplog.text


def test_gemini_provider_does_not_fallback_on_auth_400() -> None:
    settings = Settings(gemini_api_key=SecretStr("AIza-bad-key"))
    provider = GeminiLLMProvider(settings, max_retries=0, backoff_base_seconds=0.0)

    auth_err = genai_errors.APIError(
        400,
        {"error": {"message": "API key not valid. Please pass a valid API key."}},
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = auth_err

    with patch("app.ai.gemini_provider.genai.Client", return_value=mock_client):
        with pytest.raises(AIProviderError, match="API key not valid"):
            provider.generate_structured_output(
                DocumentClassificationOutput,
                "Classify notes",
                model_tier="fast",
                prompt_name="document_classification",
                prompt_version="v1",
            )

    assert mock_client.models.generate_content.call_count == 1


def test_gemini_provider_fails_over_on_429_quota_across_models_and_keys() -> None:
    settings = Settings(
        gemini_api_key=SecretStr("AIza-primary-key"),
        gemini_api_keys="AIza-backup-key",
        gemini_model_fast="gemini-2.5-flash",
        gemini_fallback_models="gemini-2.5-flash-lite",
    )
    provider = GeminiLLMProvider(
        settings,
        api_key_override="AIza-byok-user-key",
        max_retries=2,
        backoff_base_seconds=5.0,
    )

    quota_err = genai_errors.APIError(
        429,
        {
            "error": {
                "message": (
                    "You exceeded your current quota "
                    "(GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 20)."
                )
            }
        },
    )
    ok_resp = SimpleNamespace(
        text=(
            '{"subject_code": "quantitative_aptitude", "material_type": "notes", '
            '"language": "en", "confidence": 0.9, "topic_candidates": [], "rationale": "ok"}'
        ),
        usage_metadata=SimpleNamespace(
            prompt_token_count=50,
            candidates_token_count=20,
            total_token_count=70,
        ),
    )

    called_keys: list[str] = []
    called_models: list[str] = []

    def _fake_client_ctor(*, api_key: str, http_options=None):
        client = MagicMock()

        def _gen(*, model: str, contents=None, config=None):
            called_keys.append(api_key)
            called_models.append(model)
            # Fail primary model on user key, succeed on fallback model without sleeping
            if model == "gemini-2.5-flash":
                raise quota_err
            return ok_resp

        client.models.generate_content.side_effect = _gen
        return client

    with patch("app.ai.gemini_provider.genai.Client", side_effect=_fake_client_ctor):
        with patch("app.ai.gemini_provider.time.sleep") as mock_sleep:
            result = provider.generate_structured_output(
                DocumentClassificationOutput,
                "Classify math notes",
                model_tier="fast",
                prompt_name="document_classification",
                prompt_version="v1",
            )

    assert result.status == "valid"
    assert result.model_name == "gemini-2.5-flash-lite"
    assert called_keys == ["AIza-byok-user-key", "AIza-byok-user-key"]
    assert called_models == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    mock_sleep.assert_not_called()


def test_extraction_batches_stay_granulated_for_small_docs_and_pack_large_docs() -> None:
    from app.models.document import DocumentChunk  # noqa: PLC0415
    from app.services.knowledge.extractor import _build_extraction_batches  # noqa: PLC0415

    pages = {i: f"Page {i} text" for i in range(1, 13)}
    small_chunks = [
        DocumentChunk(
            document_id="00000000-0000-0000-0000-000000000001",
            chunk_index=i,
            page_start=i + 1,
            page_end=i + 1,
            chunk_type="question_block",
            content_text=f"Q.{i + 1} sample stem?",
        )
        for i in range(4)
    ]
    assert len(_build_extraction_batches(small_chunks, pages)) == 4

    many_chunks = [
        DocumentChunk(
            document_id="00000000-0000-0000-0000-000000000001",
            chunk_index=i,
            page_start=i + 1,
            page_end=i + 1,
            chunk_type="question_block",
            content_text=f"Q.{i + 1} sample stem?",
        )
        for i in range(12)
    ]
    batched = _build_extraction_batches(many_chunks, pages)
    assert len(batched) == 2
    assert len(batched[0]) == 8
    assert len(batched[1]) == 4
