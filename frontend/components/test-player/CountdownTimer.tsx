"use client";

import * as React from "react";
import { Clock } from "lucide-react";

import { cn } from "@/lib/utils/cn";
import { formatCountdownClock } from "@/lib/utils/timer";

interface CountdownTimerProps {
  remainingMs: number | null;
  label?: string;
}

export function CountdownTimer({
  remainingMs,
  label = "Remaining",
}: CountdownTimerProps) {
  const [milestoneNotice, setMilestoneNotice] = React.useState<string>("");
  const lastMilestoneRef = React.useRef<number | null>(null);

  const secondsLeft =
    remainingMs !== null ? Math.max(0, Math.ceil(remainingMs / 1000)) : null;

  React.useEffect(() => {
    if (secondsLeft === null) return;
    if (
      (secondsLeft === 30 || secondsLeft === 10 || secondsLeft === 0) &&
      lastMilestoneRef.current !== secondsLeft
    ) {
      lastMilestoneRef.current = secondsLeft;
      setMilestoneNotice(
        secondsLeft === 0
          ? "Time expired."
          : `${secondsLeft} seconds remaining.`,
      );
    }
  }, [secondsLeft]);

  if (remainingMs === null) {
    return (
      <div className="inline-flex items-center gap-1.5 rounded-md border bg-muted/40 px-2.5 py-1 text-xs font-medium text-muted-foreground">
        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Untimed (Learning Mode)</span>
      </div>
    );
  }

  const isCritical = secondsLeft !== null && secondsLeft <= 10;
  const isWarning =
    secondsLeft !== null && secondsLeft > 10 && secondsLeft <= 30;

  return (
    <div className="inline-flex items-center gap-2">
      <div
        aria-live="off"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-sm font-semibold tabular-nums",
          isCritical
            ? "border-red-300 bg-red-50 text-red-700"
            : isWarning
              ? "border-amber-300 bg-amber-50 text-amber-800"
              : "bg-card text-foreground",
        )}
      >
        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="sr-only">{label}: </span>
        <span>{formatCountdownClock(remainingMs)}</span>
      </div>
      <span className="sr-only" aria-live="polite">
        {milestoneNotice}
      </span>
    </div>
  );
}
