from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from sympy import Eq, Float, Integer, Rational, Symbol, solve
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from app.services.question_validation.option_checks import parse_canonical_numeric

_SYMPY_TRANSFORMS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

_SAFE_SYMPY_GLOBALS: dict[str, object] = {
    "Integer": Integer,
    "Float": Float,
    "Rational": Rational,
    "Symbol": Symbol,
}

_PCT_OF_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# Matches explicit equations in explanations like "250 - 200 = 50" or "20% of 250 = 50"
_NUMERIC_EQ_RE = re.compile(
    r"(?<![A-Za-z_])"
    r"([0-9][0-9\s+\-*/().%^]*?(?:\bof\b\s*[0-9][0-9\s+\-*/().%^]*?)?)"
    r"\s*=\s*"
    r"([+-]?[0-9][0-9\s+\-*/().%^]*)"
    r"(?![A-Za-z_])"
)

# Matches algebraic equations with one variable like "2x + 4 = 10" or "x + 5 = 12"
_ALGEBRAIC_EQ_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"((?:[0-9(][0-9A-Za-z\s+\-*/().^]*)|(?:[A-Za-z]\s*[+\-*/^]\s*[0-9A-Za-z\s+\-*/().^]+))"
    r"\s*=\s*"
    r"([+-]?[0-9A-Za-z\s+\-*/().^]+)"
    r"(?![A-Za-z0-9_])"
)

# Matches direct arithmetic prompts like "What is 20% of 250?" or "Evaluate 15 * 4 + 10"
_DIRECT_EXPR_RE = re.compile(
    r"(?:what\s+is|find\s+the\s+value\s+of|evaluate|calculate|solve|simplify)\s*:?\s*"
    r"([0-9(][0-9\s+\-*/().%^]*(?:\bof\b\s*[0-9(][0-9\s+\-*/().%^]*)*)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class MathCheckResult:
    """Deterministic arithmetic/equation verification outcome."""

    checked: bool
    is_consistent: bool
    expected_value: float | None = None
    matched_option_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _preprocess_math_expr(raw: str) -> str:
    cleaned = raw.strip().rstrip("?.!,;:")
    cleaned = _PCT_OF_RE.sub(r"((\1 / 100) * \2)", cleaned)
    cleaned = _PCT_RE.sub(r"(\1 / 100)", cleaned)
    return cleaned


def _eval_pure_numeric(raw: str) -> float | None:
    expr_str = _preprocess_math_expr(raw)
    if not expr_str or re.search(r"[A-Za-z_]", expr_str):
        return None
    if not re.search(r"\d", expr_str):
        return None
    try:
        val = parse_expr(
            expr_str,
            local_dict={},
            global_dict=_SAFE_SYMPY_GLOBALS,
            transformations=_SYMPY_TRANSFORMS,
        )
        if getattr(val, "free_symbols", None):
            return None
        return float(val.evalf())
    except Exception:
        return None


def _solve_single_var_equation(stem: str) -> float | None:
    """Solve simple single-variable equations like 'If 2x + 4 = 10, find x'."""
    for match in _ALGEBRAIC_EQ_RE.finditer(stem):
        lhs_raw, rhs_raw = match.group(1).strip(), match.group(2).strip()
        # Only attempt if expression tokens look purely algebraic (letters are single-char vars)
        combined = f"{lhs_raw} {rhs_raw}"
        words = re.findall(r"[A-Za-z]+", combined)
        if not words or any(len(w) > 1 for w in words) or len(set(words)) != 1:
            continue
        var_name = words[0]
        if not re.search(r"\d", combined):
            continue
        try:
            sym = Symbol(var_name, real=True)
            lhs_expr = parse_expr(
                _preprocess_math_expr(lhs_raw),
                local_dict={var_name: sym},
                global_dict=_SAFE_SYMPY_GLOBALS,
                transformations=_SYMPY_TRANSFORMS,
            )
            rhs_expr = parse_expr(
                _preprocess_math_expr(rhs_raw),
                local_dict={var_name: sym},
                global_dict=_SAFE_SYMPY_GLOBALS,
                transformations=_SYMPY_TRANSFORMS,
            )
            solutions = solve(Eq(lhs_expr, rhs_expr), sym)
            if len(solutions) == 1 and not solutions[0].free_symbols:
                return float(solutions[0].evalf())
        except Exception:
            continue
    return None


# Relational/algebraic English phrases right after a number/percentage indicate
# an incomplete quantity ("40% of that number", "25% more than...") rather than
# a standalone constant expression.
_RELATIONAL_TRAILING_RE = re.compile(
    r"^(?:"
    r"of\b|"
    r"percent(?:age)?\b|"
    r"per\s+(?:cent|annum)\b|"
    r"p\.?\s*a\.?\b|"
    r"times\b|"
    r"more\b|"
    r"less\b|"
    r"greater\b|"
    r"smaller\b|"
    r"larger\b|"
    r"higher\b|"
    r"lower\b|"
    r"[A-Za-z]\b"
    r")",
    re.IGNORECASE,
)


def _extract_stem_expected_value(stem: str) -> float | None:
    """Try deterministic evaluation of a direct expression or 1-variable equation in stem."""
    # First check direct arithmetic expression ("What is 20% of 250?")
    for direct_match in _DIRECT_EXPR_RE.finditer(stem):
        expr_candidate = direct_match.group(1).strip()
        trailing = stem[direct_match.end() :].lstrip()
        if _RELATIONAL_TRAILING_RE.match(trailing):
            continue
        # Avoid interpreting single-number phrases like "What is 10 percent..." without operators
        if any(op in expr_candidate for op in ("+", "-", "*", "/", "%", "^")):
            val = _eval_pure_numeric(expr_candidate)
            if val is not None:
                return val

    # Next check standalone equation in stem ("2x + 4 = 10")
    eq_val = _solve_single_var_equation(stem)
    if eq_val is not None:
        return eq_val

    # Finally check standalone pure numeric equation with '?' on RHS ("15 * 4 = ?")
    qmark_eq = re.search(
        r"([0-9(][0-9\s+\-*/().%^]*(?:\bof\b\s*[0-9(][0-9\s+\-*/().%^]*)*)\s*=\s*\?",
        stem,
        re.IGNORECASE,
    )
    if qmark_eq:
        val = _eval_pure_numeric(qmark_eq.group(1))
        if val is not None:
            return val

    return None


def verify_explanation_equations(explanation: str) -> list[str]:
    """Verify explicit pure-numeric `lhs = rhs` statements inside an explanation."""
    if not explanation or not explanation.strip():
        return []
    warnings: list[str] = []
    for match in _NUMERIC_EQ_RE.finditer(explanation):
        lhs_raw, rhs_raw = match.group(1), match.group(2)
        lhs_val = _eval_pure_numeric(lhs_raw)
        rhs_val = _eval_pure_numeric(rhs_raw)
        if lhs_val is None or rhs_val is None:
            continue
        if abs(lhs_val - rhs_val) > 1e-3:
            warnings.append(
                f"Explanation arithmetic mismatch: '{lhs_raw.strip()} = {rhs_raw.strip()}' "
                f"(expected {lhs_val:g})."
            )
    return warnings


# Matches explicit answer/option letter callouts inside explanations
_EXPLICIT_OPTION_CALLOUT_RE = re.compile(
    r"(?:"
    r"\b(?:correct\s+(?:answer|option)|right\s+(?:answer|option)|answer(?:\s+key)?|ans)\s*(?:is|:|=)\s*\(?([A-D])\)?"
    r"|"
    r"\boption\s*\(?([A-D])\)?\s+is\s+(?:correct|right)"
    r")\b",
    re.IGNORECASE,
)

# Matches trailing scalar/fraction value in assignments like "m2 = 4/3", "x = -5", "profit = 25%"
_CONCLUDED_EQ_VALUE_RE = re.compile(
    r"=\s*([+-]?\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*%?)(?=\s*(?:[.,;)\]]|\b|$))"
)


def verify_explanation_answer_consistency(
    *,
    options: Sequence[tuple[str, str]],
    correct_option_key: str | None,
    explanation: str,
) -> tuple[list[str], list[str]]:
    """Detect conflicts between an explanation's stated answer and `correct_option_key`."""
    if not explanation or not explanation.strip() or not correct_option_key:
        return [], []

    cleaned_key = correct_option_key.strip().upper()
    norm_opts = [(str(k or "").strip().upper(), str(t or "").strip()) for k, t in options]
    opt_text_by_key = {k: t for k, t in norm_opts if k}
    if cleaned_key not in opt_text_by_key:
        return [], []

    warnings: list[str] = []
    matched_keys: list[str] = []

    cited = {
        (m.group(1) or m.group(2)).upper()
        for m in _EXPLICIT_OPTION_CALLOUT_RE.finditer(explanation)
        if (m.group(1) or m.group(2))
    }
    if len(cited) == 1:
        cited_key = next(iter(cited))
        if cited_key in opt_text_by_key and cited_key != cleaned_key:
            warnings.append(
                f"Explanation explicitly states option '{cited_key}', "
                f"conflicting with keyed answer '{cleaned_key}'."
            )
            matched_keys.append(cited_key)
            return warnings, matched_keys

    # Compare the final concluded numeric/fraction value (if >= 2 options are numeric)
    numeric_opts: dict[str, Fraction] = {}
    for k, text in norm_opts:
        val = parse_canonical_numeric(text)
        if val is not None:
            numeric_opts[k] = val

    if len(numeric_opts) >= 2:
        eq_matches = list(_CONCLUDED_EQ_VALUE_RE.finditer(explanation))
        if eq_matches:
            last_raw = eq_matches[-1].group(1).strip()
            last_val = parse_canonical_numeric(last_raw)
            if last_val is not None:
                val_matches = [
                    k
                    for k, frac in numeric_opts.items()
                    if abs(float(frac) - float(last_val)) <= 1e-4
                ]
                if len(val_matches) == 1 and val_matches[0] != cleaned_key:
                    m_key = val_matches[0]
                    # Do not flag when keyed option has numerically identical value
                    keyed_val = numeric_opts.get(cleaned_key)
                    if keyed_val is None or abs(float(keyed_val) - float(last_val)) > 1e-4:
                        warnings.append(
                            f"Explanation concludes '{last_raw}' (matches option '{m_key}': "
                            f"'{opt_text_by_key[m_key]}'), "
                            f"conflicting with keyed answer '{cleaned_key}'."
                        )
                        matched_keys.append(m_key)

    return warnings, matched_keys


def verify_question_math(
    *,
    question_text: str,
    options: Sequence[tuple[str, str]],
    correct_option_key: str | None,
    explanation: str = "",
) -> MathCheckResult:
    """Deterministically verify mathematical stems, explanations, and option values."""
    warnings: list[str] = []
    warnings.extend(verify_explanation_equations(explanation))
    exp_warnings, exp_matched_keys = verify_explanation_answer_consistency(
        options=options,
        correct_option_key=correct_option_key,
        explanation=explanation,
    )
    warnings.extend(exp_warnings)

    expected = _extract_stem_expected_value(question_text)
    if expected is None:
        return MathCheckResult(
            checked=bool(warnings or exp_matched_keys),
            is_consistent=len(warnings) == 0,
            expected_value=None,
            matched_option_keys=exp_matched_keys,
            warnings=warnings,
        )

    option_values: dict[str, Fraction] = {}
    for key, text in options:
        parsed = parse_canonical_numeric(text)
        if parsed is not None:
            option_values[key.strip().upper()] = parsed

    if not option_values:
        # Options are non-numeric (e.g. text/ratios), only keep explanation warnings if any
        return MathCheckResult(
            checked=bool(warnings),
            is_consistent=len(warnings) == 0,
            expected_value=expected,
            matched_option_keys=[],
            warnings=warnings,
        )

    matched_keys = [
        key for key, frac_val in option_values.items() if abs(float(frac_val) - expected) <= 1e-4
    ]

    if len(matched_keys) > 1:
        warnings.append(
            f"Multiple options ({', '.join(matched_keys)}) match deterministic value {expected:g}."
        )
    elif len(matched_keys) == 0:
        warnings.append(
            f"No option matches deterministic math result {expected:g}."
        )
    elif correct_option_key:
        cleaned_key = correct_option_key.strip().upper()
        if cleaned_key not in matched_keys:
            warnings.append(
                f"Keyed answer '{cleaned_key}' disagrees with deterministic math check "
                f"(computed {expected:g}, matching option '{matched_keys[0]}')."
            )

    return MathCheckResult(
        checked=True,
        is_consistent=len(warnings) == 0,
        expected_value=expected,
        matched_option_keys=matched_keys,
        warnings=warnings,
    )
