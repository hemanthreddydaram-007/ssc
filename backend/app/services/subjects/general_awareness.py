from __future__ import annotations

from app.models.learning import Concept, Fact
from app.schemas.notes import NoteBlock, NoteContentJson, NoteSection
from app.services.subjects.base import SubjectAdapter, SubjectValidationReport


class GeneralAwarenessSubjectAdapter(SubjectAdapter):
    """Subject adapter for General Awareness / Current Affairs (Section 3.2.C)."""

    subject_code = "general_awareness"
    display_name = "General Awareness"
    supported_strategies = [
        "five_ws_summary",
        "factual_tables",
        "timeline_sequence",
        "static_vs_current_flagging",
    ]

    def strategy_instructions(self) -> str:
        return (
            "Structure sections for General Awareness / Current Affairs:\n"
            "1. five_ws_breakdown: Who / What / When / Where / Why with ministry, organisation, "
            "location, date, and beneficiary fields where applicable.\n"
            "2. structured_tables_and_timeline: Short factual tables and chronological sequence.\n"
            "3. static_vs_current: Explicitly separate current/time-sensitive facts from static "
            "background facts, and flag facts whose correctness may have changed since publication."
        )

    def validate_note_content(
        self,
        content: NoteContentJson,
        *,
        source_facts: list[Fact],
        source_concepts: list[Concept],
    ) -> SubjectValidationReport:
        report = SubjectValidationReport()
        time_sensitive_facts = [f for f in source_facts if f.is_time_sensitive]
        if not time_sensitive_facts:
            return report

        has_staleness_warning = any(
            block.block_type == "warning"
            or "changed since" in block.body.lower()
            or "time-sensitive" in block.body.lower()
            for section in content.sections
            for block in section.blocks
        )
        if not has_staleness_warning:
            date_labels = sorted(
                {f.source_date_label for f in time_sensitive_facts if f.source_date_label}
            )
            date_note = (
                f" (source date context: {', '.join(date_labels)})" if date_labels else ""
            )
            content.sections.append(
                NoteSection(
                    key="staleness_notice",
                    title="Time-Sensitive Fact Notice",
                    blocks=[
                        NoteBlock(
                            block_type="warning",
                            title="Verify Current Status",
                            body=(
                                f"This topic includes {len(time_sensitive_facts)} time-sensitive "
                                f"fact(s){date_note} whose current accuracy may have changed "
                                "since the source material was published."
                            ),
                            provenance="ai_explanation",
                            source_refs=[],
                            review_status="needs_review",
                        )
                    ],
                )
            )
            report.warnings.append(
                "Topic contains time-sensitive General Awareness facts; staleness warning added."
            )
        return report
