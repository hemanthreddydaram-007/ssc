from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction

_ALLOWED_SINGLE_CHOICE_KEYS = ("A", "B", "C", "D")

_PURE_PERCENT_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*%\s*$")
_PURE_FRACTION_RE = re.compile(r"^\s*([+-]?\d+)\s*/\s*([+-]?\d+)\s*$")
_PURE_NUMBER_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*$")


@dataclass(slots=True)
class OptionCheckResult:
    """Result of structural, uniqueness, and canonical equivalence checks on MCQ options."""

    is_valid: bool
    normalized_options: list[tuple[str, str]]
    correct_option_key: str | None
    warnings: list[str] = field(default_factory=list)


def parse_canonical_numeric(text: str) -> Fraction | None:
    """Parse pure numeric, fraction, or percentage text into an exact `Fraction`.

    Examples:
        "0.5" -> Fraction(1, 2)
        "1/2" -> Fraction(1, 2)
        "50%" -> Fraction(1, 2)
        "1,250" -> Fraction(1250, 1)
    """
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return None

    # Strip thousand-grouping commas inside numbers (e.g., "1,200" -> "1200")
    no_commas = re.sub(r"(?<=\d),(?=\d{3}\b)", "", cleaned)

    pct_match = _PURE_PERCENT_RE.match(no_commas)
    if pct_match:
        try:
            return Fraction(pct_match.group(1)) / 100
        except (ValueError, ZeroDivisionError):
            return None

    frac_match = _PURE_FRACTION_RE.match(no_commas)
    if frac_match:
        try:
            denom = int(frac_match.group(2))
            if denom == 0:
                return None
            return Fraction(int(frac_match.group(1)), denom)
        except ValueError:
            return None

    num_match = _PURE_NUMBER_RE.match(no_commas)
    if num_match:
        try:
            return Fraction(num_match.group(1))
        except ValueError:
            return None

    return None


def check_single_choice_options(
    options: Sequence[tuple[str, str]],
    correct_option_key: str | None,
) -> OptionCheckResult:
    """Validate 4 distinct A-D options, canonical numeric uniqueness, and answer key."""
    warnings: list[str] = []
    normalized: list[tuple[str, str]] = []
    for raw_key, raw_text in options:
        key = str(raw_key or "").strip().upper()
        text = " ".join(str(raw_text or "").split()).strip()
        normalized.append((key, text))

    if len(normalized) != 4:
        warnings.append(
            f"Single-choice question must have exactly 4 options (found {len(normalized)})."
        )

    keys = [k for k, _ in normalized]
    if any(not k for k in keys) or any(not t for _, t in normalized):
        warnings.append("All option keys and option texts must be non-empty.")

    if len(set(keys)) != len(keys):
        warnings.append("Duplicate option keys detected.")

    if set(keys) != set(_ALLOWED_SINGLE_CHOICE_KEYS) and len(normalized) == 4:
        warnings.append("Single-choice option keys must be A, B, C, and D.")

    seen_texts: dict[str, str] = {}
    for key, text in normalized:
        lowered = text.lower()
        if not lowered:
            continue
        if lowered in seen_texts:
            warnings.append(
                f"Duplicate option text between '{seen_texts[lowered]}' and '{key}': '{text}'."
            )
        else:
            seen_texts[lowered] = key

    seen_numeric: dict[Fraction, tuple[str, str]] = {}
    for key, text in normalized:
        val = parse_canonical_numeric(text)
        if val is None:
            continue
        if val in seen_numeric:
            prev_key, prev_text = seen_numeric[val]
            # Avoid double-reporting if exact text was already identical
            if prev_text.lower() != text.lower():
                warnings.append(
                    f"Equivalent numeric options detected between '{prev_key}' ({prev_text}) "
                    f"and '{key}' ({text})."
                )
        else:
            seen_numeric[val] = (key, text)

    cleaned_key = str(correct_option_key).strip().upper() if correct_option_key else None
    if not cleaned_key:
        warnings.append("Missing correct_option_key.")
    elif cleaned_key not in set(_ALLOWED_SINGLE_CHOICE_KEYS) or cleaned_key not in set(keys):
        warnings.append(f"Invalid correct_option_key '{cleaned_key}' for options {keys}.")

    return OptionCheckResult(
        is_valid=len(warnings) == 0,
        normalized_options=normalized,
        correct_option_key=cleaned_key,
        warnings=warnings,
    )
