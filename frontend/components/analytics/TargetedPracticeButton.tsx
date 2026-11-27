"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Target } from "lucide-react";

import { Button } from "@/components/ui/button";
import { startTestAttempt } from "@/lib/api/attempts";
import { launchTargetedPractice } from "@/lib/api/performance";

interface TargetedPracticeButtonProps {
  topicIds: string[];
  sourceAttemptId?: string;
  label?: string;
  timerMode?: "learning_mode" | "speed_challenge";
  questionCount?: number;
  size?: "sm" | "default";
  variant?: "default" | "outline";
}

export function TargetedPracticeButton({
  topicIds,
  sourceAttemptId,
  label = "Start Targeted Practice",
  timerMode = "learning_mode",
  questionCount = 10,
  size = "sm",
  variant = "default",
}: TargetedPracticeButtonProps) {
  const router = useRouter();
  const [isLaunching, setIsLaunching] = React.useState(false);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  const handleLaunch = async () => {
    if (topicIds.length === 0) return;
    setIsLaunching(true);
    setErrorMsg(null);
    try {
      const created = await launchTargetedPractice({
        topic_ids: topicIds,
        source_attempt_id: sourceAttemptId,
        question_count: questionCount,
        difficulty_progression: "easy_to_medium",
        timer_mode: timerMode,
        per_question_seconds: 35,
      });
      const attempt = await startTestAttempt(created.test.id);
      router.push(`/attempts/${encodeURIComponent(attempt.attempt_id)}`);
    } catch (error) {
      setErrorMsg(
        error instanceof Error
          ? error.message
          : "Unable to create targeted practice.",
      );
      setIsLaunching(false);
    }
  };

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <Button
        type="button"
        size={size}
        variant={variant}
        disabled={isLaunching || topicIds.length === 0}
        onClick={() => void handleLaunch()}
      >
        <Target className="h-3.5 w-3.5" aria-hidden="true" />
        <span>{isLaunching ? "Starting…" : label}</span>
      </Button>
      {errorMsg ? (
        <span className="inline-flex items-center gap-1 text-xs text-destructive">
          <AlertCircle className="h-3 w-3 shrink-0" aria-hidden="true" />
          {errorMsg}
        </span>
      ) : null}
    </div>
  );
}
