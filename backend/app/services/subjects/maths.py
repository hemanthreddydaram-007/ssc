from __future__ import annotations

import re

from sympy import Float, Integer, Rational
from sympy.parsing.sympy_parser import parse_expr

from app.models.learning import Concept, Fact
from app.schemas.notes import NoteContentJson
from app.services.subjects.base import SubjectAdapter, SubjectValidationReport

_SAFE_SYMPY_GLOBALS: dict[str, object] = {
    "Integer": Integer,
    "Float": Float,
    "Rational": Rational,
}

# Matches numeric equations like "250 - 200 = 50", "(50 / 200) * 100 = 25", or "20% of 200 = 40"
_NUMERIC_EQ_RE = re.compile(
    r"(?<![A-Za-z_])"
    r"([0-9][0-9\s+\-*/().%]*?(?:\bof\b\s*[0-9][0-9\s+\-*/().%]*?)?)"
    r"\s*=\s*"
    r"([0-9][0-9\s+\-*/().%]*)"
    r"(?![A-Za-z_])"
)
_PCT_OF_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _prepare_numeric_expr(raw: str) -> str | None:
    cleaned = raw.strip().rstrip(".,;:")
    if not cleaned:
        return None
    if re.search(r"[A-Za-z]", _PCT_OF_RE.sub("", cleaned)):
        return None
    converted = _PCT_OF_RE.sub(r"((\1 / 100) * \2)", cleaned)
    converted = _PCT_RE.sub(r"(\1 / 100)", converted)
    # Reject dangling operators or empty parens
    if not re.search(r"\d", converted):
        return None
    return converted


def verify_numeric_equations(text: str) -> list[str]:
    """Deterministically verify pure numeric `lhs = rhs` equations in text via SymPy."""
    mismatches: list[str] = []
    for match in _NUMERIC_EQ_RE.finditer(text):
        lhs_raw, rhs_raw = match.group(1), match.group(2)
        lhs_expr_str = _prepare_numeric_expr(lhs_raw)
        rhs_expr_str = _prepare_numeric_expr(rhs_raw)
        if not lhs_expr_str or not rhs_expr_str:
            continue
        try:
            lhs_val = parse_expr(lhs_expr_str, local_dict={}, global_dict=_SAFE_SYMPY_GLOBALS)
            rhs_val = parse_expr(rhs_expr_str, local_dict={}, global_dict=_SAFE_SYMPY_GLOBALS)
            if lhs_val.free_symbols or rhs_val.free_symbols:
                continue
            diff = abs(float(lhs_val.evalf()) - float(rhs_val.evalf()))
            if diff > 1e-3:
                mismatches.append(
                    f"Arithmetic mismatch: '{lhs_raw.strip()} = {rhs_raw.strip()}' "
                    f"(expected {float(lhs_val.evalf()):g})"
                )
        except Exception:
            continue
    return mismatches


class MathsSubjectAdapter(SubjectAdapter):
    """Subject adapter for Quantitative Aptitude / Maths (Section 3.2.C)."""

    subject_code = "quantitative_aptitude"
    display_name = "Quantitative Aptitude / Maths"
    supported_strategies = [
        "standard_method",
        "alternative_method",
        "shortcut_with_assumptions",
        "calculation_traps",
    ]

    def strategy_instructions(self) -> str:
        return (
            "Structure sections for Maths / Quantitative Aptitude:\n"
            "1. standard_method: Standard textbook method and step-by-step worked example.\n"
            "2. alternative_method: Valid alternative solving approach where applicable.\n"
            "3. shortcut_method: Faster shortcut ONLY if mathematically justified, explicitly "
            "stating formula, assumptions, and when_safe_to_use in metadata.\n"
            "4. calculation_traps: Common calculation errors and time comparisons labeled "
            "strictly as estimates (never measured guarantees)."
        )

    def validate_note_content(
        self,
        content: NoteContentJson,
        *,
        source_facts: list[Fact],
        source_concepts: list[Concept],
    ) -> SubjectValidationReport:
        report = SubjectValidationReport()
        for section in content.sections:
            for block in section.blocks:
                if block.block_type not in (
                    "worked_example",
                    "formula",
                    "step",
                    "strategy",
                    "concept",
                ):
                    continue
                check_text = block.body
                if block.formula_latex:
                    check_text = f"{check_text}\n{block.formula_latex}"
                mismatches = verify_numeric_equations(check_text)
                if mismatches:
                    block.review_status = "needs_review"
                    block.metadata["math_verification_warnings"] = mismatches
                    report.warnings.extend(mismatches)
                    report.flagged_block_count += 1
        return report
