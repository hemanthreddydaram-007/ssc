from __future__ import annotations

from app.ai.mock_provider import MockLLMProvider
from app.services.question_validation.math_solver import verify_question_math
from app.services.question_validation.option_checks import (
    check_single_choice_options,
    parse_canonical_numeric,
)
from app.services.question_validation.validator import QuestionValidationService


def test_option_checks_detect_equivalent_numeric_values() -> None:
    assert parse_canonical_numeric("0.5") == parse_canonical_numeric("1/2")
    assert parse_canonical_numeric("50%") == parse_canonical_numeric("0.5")

    res = check_single_choice_options(
        [("A", "0.5"), ("B", "1/2"), ("C", "0.75"), ("D", "1.0")],
        "A",
    )
    assert res.is_valid is False
    assert any("Equivalent numeric options" in w for w in res.warnings)


def test_option_checks_reject_missing_or_duplicate_options() -> None:
    res = check_single_choice_options(
        [("A", "Kind"), ("B", "Kind"), ("C", "Cruel")],
        "D",
    )
    assert res.is_valid is False
    assert len(res.warnings) >= 3


def test_math_solver_catches_wrong_key_and_explanation_error() -> None:
    wrong_key = verify_question_math(
        question_text="What is 20% of 250?",
        options=[("A", "40"), ("B", "50"), ("C", "60"), ("D", "75")],
        correct_option_key="A",
        explanation="20% of 250 = 40.",
    )
    assert wrong_key.checked is True
    assert wrong_key.is_consistent is False
    assert wrong_key.matched_option_keys == ["B"]
    assert any("disagrees" in w for w in wrong_key.warnings)
    assert any("Explanation arithmetic mismatch" in w for w in wrong_key.warnings)

    algebra_ok = verify_question_math(
        question_text="If 2x + 4 = 10, find x.",
        options=[("A", "2"), ("B", "3"), ("C", "4"), ("D", "5")],
        correct_option_key="B",
        explanation="2 * 3 + 4 = 10.",
    )
    assert algebra_ok.checked is True
    assert algebra_ok.is_consistent is True
    assert algebra_ok.matched_option_keys == ["B"]


def test_validation_service_blocks_unverified_user_supplied_and_uses_llm_hook() -> None:
    mock_llm = MockLLMProvider()
    svc = QuestionValidationService(llm_provider=mock_llm)

    # User-supplied non-math key must remain needs_review (never auto-verified)
    user_supplied = svc.validate_question(
        question_text="Who wrote the Discovery of India?",
        question_type="single_choice",
        subject_code="general_awareness",
        options=[
            ("A", "Mahatma Gandhi"),
            ("B", "Jawaharlal Nehru"),
            ("C", "Sardar Patel"),
            ("D", "B.R. Ambedkar"),
        ],
        correct_option_key="B",
        explanation="Written by Jawaharlal Nehru.",
        origin="manual",
        answer_key_provenance="user_supplied",
    )
    assert user_supplied.validation_status == "needs_review"

    # Deterministic math check upgrades generated arithmetic question to verified
    math_verified = svc.validate_question(
        question_text="What is 25% of 80?",
        question_type="single_choice",
        subject_code="quantitative_aptitude",
        options=[("A", "15"), ("B", "20"), ("C", "25"), ("D", "30")],
        correct_option_key="B",
        explanation="25% of 80 = 20.",
        origin="generated",
        answer_key_provenance="ai_verified",
        run_llm_verify=True,
    )
    assert math_verified.validation_status == "verified"
    assert math_verified.answer_key_provenance == "deterministic_solver"
    assert math_verified.llm_verified is True
