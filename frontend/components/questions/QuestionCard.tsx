"use client";

import { Eye, FileText } from "lucide-react";

import { AuthAssetImage } from "@/components/common/AuthAssetImage";
import { RichMathText } from "@/components/common/MathRenderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import type { QuestionOut } from "@/lib/api/questions";

interface QuestionCardProps {
  question: QuestionOut;
  selected: boolean;
  onToggleSelect: (questionId: string) => void;
  onInspect: (questionId: string) => void;
}

export function getValidationBadgeVariant(
  status: string,
): "success" | "warning" | "destructive" | "secondary" {
  switch (status.toLowerCase()) {
    case "verified":
      return "success";
    case "needs_review":
      return "warning";
    case "rejected":
      return "destructive";
    default:
      return "secondary";
  }
}

export function QuestionCard({
  question,
  selected,
  onToggleSelect,
  onInspect,
}: QuestionCardProps) {
  const sortedOptions = [...question.options].sort(
    (a, b) => (a.display_order ?? 0) - (b.display_order ?? 0),
  );

  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(question.id)}
            aria-label={`Select question ${question.question_text.slice(0, 40)}`}
            className="mt-1 h-4 w-4 rounded border-input"
          />
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="outline">
              {formatSubjectLabel(question.subject_code)}
            </Badge>
            {question.topic_name ? (
              <Badge variant="outline">{question.topic_name}</Badge>
            ) : null}
            <Badge variant="secondary" className="capitalize">
              {question.difficulty}
            </Badge>
            <Badge variant="outline" className="capitalize">
              {question.origin}
            </Badge>
            <Badge
              variant={getValidationBadgeVariant(question.validation_status)}
            >
              {question.validation_status.replace(/_/g, " ")}
            </Badge>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onInspect(question.id)}
        >
          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Inspect &amp; Answer</span>
        </Button>
      </div>

      {question.passage_text ? (
        <div className="rounded-md border bg-muted/40 p-2.5 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">Passage: </span>
          {question.passage_text.slice(0, 220)}
          {question.passage_text.length > 220 ? "…" : ""}
        </div>
      ) : null}

      <div className="text-sm font-medium text-foreground">
        <RichMathText text={question.question_text} />
      </div>

      {question.diagram_asset_id && question.document_id ? (
        <div className="overflow-hidden rounded-md border bg-muted/20 p-2">
          <AuthAssetImage
            documentId={question.document_id}
            assetId={question.diagram_asset_id}
            alt="Question diagram"
            className="mx-auto max-h-40 w-auto rounded object-contain"
          />
        </div>
      ) : null}

      {sortedOptions.length > 0 ? (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {sortedOptions.map((opt) => (
            <div
              key={opt.option_key}
              className="flex items-start gap-2 rounded-md border bg-muted/20 px-3 py-1.5 text-xs"
            >
              <span className="font-semibold text-muted-foreground">
                ({opt.option_key})
              </span>
              <span className="text-foreground">
                <RichMathText text={opt.option_text} />
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          Key provenance: {question.answer_key_provenance.replace(/_/g, " ")}
        </span>
        {question.source_page_number ? (
          <span className="inline-flex items-center gap-1">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            Page {question.source_page_number}
          </span>
        ) : null}
      </div>
    </div>
  );
}
