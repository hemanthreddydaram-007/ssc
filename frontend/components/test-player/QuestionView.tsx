"use client";

import { Bookmark, CheckCircle2, XCircle } from "lucide-react";

import { AuthAssetImage } from "@/components/common/AuthAssetImage";
import { RichMathText } from "@/components/common/MathRenderer";
import { Badge } from "@/components/ui/badge";
import {
  getOptionKey,
  getOptionText,
  type LockedFeedbackOut,
  type PlayerQuestionOut,
} from "@/lib/api/attempts";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import { cn } from "@/lib/utils/cn";

interface QuestionViewProps {
  question: PlayerQuestionOut;
  selectedOptionKey: string | null;
  lockedFeedback?: LockedFeedbackOut | null;
  disabled: boolean;
  onSelectOption: (optionKey: string) => void;
}

export function QuestionView({
  question,
  selectedOptionKey,
  lockedFeedback,
  disabled,
  onSelectOption,
}: QuestionViewProps) {
  const feedback = lockedFeedback ?? question.locked_feedback;
  const isLocked =
    Boolean(feedback) ||
    Boolean(question.is_locked) ||
    question.status === "timed_out";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
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
        </div>

        {question.is_marked_for_review ? (
          <Badge variant="warning" className="gap-1">
            <Bookmark className="h-3 w-3" aria-hidden="true" />
            Marked for review
          </Badge>
        ) : null}
      </div>

      {question.passage_text ? (
        <div className="max-h-56 overflow-y-auto rounded-md border bg-muted/40 p-4 text-sm">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Reading Passage
          </p>
          <RichMathText text={question.passage_text} />
        </div>
      ) : null}

      {question.diagram_asset_id && question.document_id ? (
        <div className="overflow-hidden rounded-md border bg-muted/20 p-3">
          <AuthAssetImage
            documentId={question.document_id}
            assetId={question.diagram_asset_id}
            alt={`Diagram for question ${question.display_order + 1}`}
            className="mx-auto max-h-64 w-auto rounded object-contain"
          />
        </div>
      ) : null}

      <div className="text-base font-medium leading-relaxed text-foreground sm:text-lg">
        <RichMathText text={question.question_text} />
      </div>

      <fieldset disabled={disabled || isLocked} className="space-y-2.5">
        <legend className="sr-only">Answer options</legend>
        {question.options.map((opt, idx) => {
          const optKey = getOptionKey(opt);
          const optText = getOptionText(opt);
          const isSelected = selectedOptionKey === optKey;
          const isCorrectChoice =
            feedback?.correct_option_key === optKey;
          const isWrongChoice =
            feedback &&
            feedback.selected_option_key === optKey &&
            feedback.is_correct === false;

          return (
            <button
              key={optKey}
              type="button"
              role="radio"
              aria-checked={isSelected}
              onClick={() => onSelectOption(optKey)}
              disabled={disabled || isLocked}
              className={cn(
                "flex min-h-[48px] w-full items-start gap-3 rounded-lg border px-4 py-3 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default sm:text-base",
                isCorrectChoice
                  ? "border-emerald-400 bg-emerald-50 text-emerald-950"
                  : isWrongChoice
                    ? "border-red-400 bg-red-50 text-red-950"
                    : isSelected
                      ? "border-primary bg-primary/10 text-foreground"
                      : "bg-card hover:border-primary/50 hover:bg-muted/40",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                  isSelected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-muted-foreground/40 text-muted-foreground",
                )}
              >
                {optKey}
              </span>
              <span className="min-w-0 flex-1 break-words">
                <RichMathText text={optText} />
              </span>
              <span className="hidden text-[11px] text-muted-foreground sm:inline">
                [{idx + 1}]
              </span>
            </button>
          );
        })}
      </fieldset>

      {feedback ? (
        <div
          role="status"
          aria-live="polite"
          className={cn(
            "rounded-lg border p-4 space-y-2",
            feedback.is_correct
              ? "border-emerald-300 bg-emerald-50/70"
              : "border-amber-300 bg-amber-50/70",
          )}
        >
          <div className="flex items-center gap-2 font-semibold text-sm">
            {feedback.is_correct ? (
              <>
                <CheckCircle2
                  className="h-4 w-4 text-emerald-600"
                  aria-hidden="true"
                />
                <span className="text-emerald-900">Correct!</span>
              </>
            ) : (
              <>
                <XCircle className="h-4 w-4 text-red-600" aria-hidden="true" />
                <span className="text-red-900">
                  Incorrect — Correct answer:{" "}
                  {feedback.correct_option_key ?? "N/A"}
                </span>
              </>
            )}
          </div>
          {feedback.explanation ? (
            <div className="text-sm text-foreground">
              <RichMathText text={feedback.explanation} />
            </div>
          ) : (
            <p className="text-xs italic text-muted-foreground">
              No written explanation recorded for this question yet.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
