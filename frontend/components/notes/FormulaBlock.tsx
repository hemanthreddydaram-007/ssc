"use client";

import { MathRenderer, RichMathText } from "@/components/common/MathRenderer";
import { ProvenanceBadge } from "@/components/notes/ProvenanceBadge";
import { SourceCitationLink } from "@/components/notes/SourceCitationLink";
import { Badge } from "@/components/ui/badge";
import type { NoteBlockOut } from "@/lib/api/notes";
import { cn } from "@/lib/utils/cn";

interface FormulaBlockProps {
  block: NoteBlockOut;
  fallbackDocumentId: string;
}

function formatBlockTypeLabel(blockType: string): string {
  return blockType
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function FormulaBlock({
  block,
  fallbackDocumentId,
}: FormulaBlockProps) {
  const isAiExplanation = block.provenance.toLowerCase() === "ai_explanation";
  const isWarning =
    block.block_type === "warning" ||
    block.block_type === "misconception" ||
    block.review_status === "needs_review" ||
    block.review_status === "conflict";

  return (
    <div
      className={cn(
        "rounded-lg border p-4 transition-colors",
        isAiExplanation
          ? "border-dashed border-sky-300 bg-sky-50/50"
          : isWarning
            ? "border-amber-200 bg-amber-50/40"
            : "bg-card",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-[11px]">
            {formatBlockTypeLabel(block.block_type)}
          </Badge>
          {block.title ? (
            <h4 className="text-sm font-semibold">{block.title}</h4>
          ) : null}
        </div>
        <ProvenanceBadge
          provenance={block.provenance}
          reviewStatus={block.review_status}
        />
      </div>

      {isAiExplanation ? (
        <p className="mt-1.5 text-[11px] font-medium text-sky-800">
          AI-generated explanation added for learning clarity — not a direct
          quotation from your uploaded source.
        </p>
      ) : null}

      <div className="mt-2.5 text-sm text-foreground">
        <RichMathText text={block.body} />
      </div>

      {block.formula_latex ? (
        <div className="mt-3 overflow-x-auto rounded-md border bg-muted/40 px-3 py-2">
          <MathRenderer latex={block.formula_latex} displayMode />
        </div>
      ) : null}

      <SourceCitationLink
        refs={block.source_refs}
        fallbackDocumentId={fallbackDocumentId}
      />
    </div>
  );
}
