from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from app.ai.gemini_provider import GeminiLLMProvider
from app.ai.mock_provider import MockLLMProvider
from app.ai.provider import AIConfigurationError, BinaryPart
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
