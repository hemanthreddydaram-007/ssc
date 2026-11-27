"use client";

import type { PaletteItemOut } from "@/lib/api/attempts";
import { cn } from "@/lib/utils/cn";

interface QuestionPaletteProps {
  palette: readonly PaletteItemOut[];
  currentIndex: number;
  allowNavigation: boolean;
  onSelectIndex: (index: number) => void;
}

export function QuestionPalette({
  palette,
  currentIndex,
  allowNavigation,
  onSelectIndex,
}: QuestionPaletteProps) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-5 gap-2 sm:grid-cols-6 lg:grid-cols-5">
        {palette.map((item) => {
          const isCurrent = item.index === currentIndex;
          const isAnswered = item.has_answer || item.status === "answered";
          const isTimedOut = item.status === "timed_out";
          const isSkipped = item.status === "skipped";

          return (
            <button
              key={item.test_question_id}
              type="button"
              disabled={!allowNavigation}
              onClick={() => onSelectIndex(item.index)}
              aria-label={`Question ${item.index + 1}${isCurrent ? " (current)" : ""}${item.is_marked_for_review ? ", marked for review" : ""}${isAnswered ? ", answered" : ""}`}
              aria-current={isCurrent ? "step" : undefined}
              className={cn(
                "relative flex min-h-[44px] min-w-[44px] w-full items-center justify-center rounded-md border text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default",
                isCurrent && "ring-2 ring-primary ring-offset-1",
                isAnswered
                  ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                  : isTimedOut
                    ? "border-red-300 bg-red-50 text-red-800"
                    : isSkipped
                      ? "border-amber-300 bg-amber-50 text-amber-900"
                      : "bg-background text-muted-foreground hover:bg-accent",
              )}
            >
              <span>{item.index + 1}</span>
              {item.is_marked_for_review ? (
                <span
                  aria-hidden="true"
                  className="absolute right-1 top-1 h-2 w-2 rounded-full bg-violet-600"
                />
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-sm border border-emerald-300 bg-emerald-50" />
          Answered
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-sm border border-amber-300 bg-amber-50" />
          Skipped
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full bg-violet-600" />
          Review
        </span>
      </div>
    </div>
  );
}
