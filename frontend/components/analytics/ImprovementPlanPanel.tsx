"use client";

import Link from "next/link";
import { BookOpen, RefreshCw, Sparkles } from "lucide-react";

import { TargetedPracticeButton } from "@/components/analytics/TargetedPracticeButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  AICoachingOut,
  AICoachingTopicExplanation,
  ImprovementPlanOut,
} from "@/lib/api/performance";
import { normalizePriority } from "@/lib/utils/number";

interface ImprovementPlanPanelProps {
  attemptId: string;
  plan: ImprovementPlanOut | null;
  isLoading: boolean;
  isGenerating: boolean;
  errorMessage: string | null;
  onGenerate: (forceRegenerate: boolean) => void;
}

function extractTopicExplanations(
  raw: AICoachingOut["topic_explanations"],
): AICoachingTopicExplanation[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw.filter(
      (item): item is AICoachingTopicExplanation =>
        typeof item === "object" &&
        item !== null &&
        typeof item.topic_name === "string" &&
        typeof item.explanation === "string" &&
        item.explanation.trim().length > 0,
    );
  }
  if (typeof raw === "object") {
    return Object.entries(raw)
      .filter(([, val]) => typeof val === "string" && val.trim().length > 0)
      .map(([topic_name, explanation]) => ({ topic_name, explanation }));
  }
  return [];
}

export function ImprovementPlanPanel({
  attemptId,
  plan,
  isLoading,
  isGenerating,
  errorMessage,
  onGenerate,
}: ImprovementPlanPanelProps) {
  const topicExplanations = plan
    ? extractTopicExplanations(plan.ai_coaching?.topic_explanations)
    : [];

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
            <CardTitle>Personalised Improvement Plan</CardTitle>
          </div>
          <CardDescription>
            Actionable recommendations backed by your recorded metrics. Topics
            with fewer than 5 attempts are marked insufficient data.
          </CardDescription>
        </div>

        <Button
          type="button"
          size="sm"
          variant={plan ? "outline" : "default"}
          disabled={isGenerating || isLoading}
          onClick={() => onGenerate(Boolean(plan))}
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isGenerating ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          <span>
            {isGenerating
              ? "Generating…"
              : plan
                ? "Refresh Plan"
                : "Generate Improvement Plan"}
          </span>
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {errorMessage ? (
          <div
            role="alert"
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
          >
            {errorMessage}
          </div>
        ) : null}

        {isLoading ? (
          <p className="text-sm text-muted-foreground">
            Loading improvement plan…
          </p>
        ) : !plan ? (
          <p className="text-sm text-muted-foreground">
            Click <strong>Generate Improvement Plan</strong> above to turn this
            attempt&apos;s metrics into concrete next steps.
          </p>
        ) : (
          <>
            {plan.ai_coaching?.summary_text ? (
              <div className="space-y-2.5 rounded-md border border-sky-200 bg-sky-50/60 p-4 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold text-sky-950">
                    Coaching Summary
                  </span>
                  <Badge variant="outline">
                    {plan.ai_coaching.status === "generated"
                      ? "AI-phrased (metric-grounded)"
                      : "Metric-backed summary"}
                  </Badge>
                </div>
                <p className="text-sky-950/90">
                  {plan.ai_coaching.summary_text}
                </p>
                {topicExplanations.length > 0 ? (
                  <ul className="space-y-1.5 border-t border-sky-200/70 pt-2.5 text-xs text-sky-950/90">
                    {topicExplanations.map((item, idx) => (
                      <li key={`${item.topic_name}-${idx}`}>
                        <span className="font-semibold">{item.topic_name}:</span>{" "}
                        {item.explanation}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {plan.recommendations.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No action items generated for this attempt.
              </p>
            ) : (
              <div className="space-y-3">
                {plan.recommendations.map((rec, idx) => {
                  const priorityTier = normalizePriority(rec.priority);
                  const firstNoteId = rec.recommended_note_ids[0];
                  const reviseHref = firstNoteId
                    ? `/notes/${encodeURIComponent(firstNoteId)}`
                    : rec.topic_id
                      ? `/notes?topic_id=${encodeURIComponent(rec.topic_id)}`
                      : "/notes";

                  return (
                    <div
                      key={`${rec.rule_id}-${rec.topic_id ?? idx}`}
                      className="space-y-3 rounded-lg border p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="font-semibold">
                            {rec.topic_name ?? "General Practice"}
                          </h4>
                          <Badge variant="outline" className="capitalize">
                            {rec.action_type.replace(/_/g, " ")}
                          </Badge>
                          <Badge
                            variant={
                              priorityTier === "high"
                                ? "destructive"
                                : priorityTier === "medium"
                                  ? "warning"
                                  : "secondary"
                            }
                            className="capitalize"
                          >
                            {priorityTier} priority
                          </Badge>
                        </div>
                        <span className="font-mono text-[11px] text-muted-foreground">
                          {rec.rule_id}
                        </span>
                      </div>

                      <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
                        <div className="rounded bg-muted/40 p-2.5">
                          <p className="font-semibold text-foreground">
                            Observation
                          </p>
                          <p className="mt-1 text-muted-foreground">
                            {rec.observation}
                          </p>
                        </div>
                        <div className="rounded bg-muted/40 p-2.5">
                          <p className="font-semibold text-foreground">
                            Possible Cause
                          </p>
                          <p className="mt-1 text-muted-foreground">
                            {rec.possible_interpretation}
                          </p>
                        </div>
                      </div>

                      <p className="text-sm font-medium text-foreground">
                        Next step: {rec.recommendation}
                      </p>

                      <div className="flex flex-wrap items-center gap-2">
                        <Button asChild variant="outline" size="sm">
                          <Link href={reviseHref}>
                            <BookOpen
                              className="h-3.5 w-3.5"
                              aria-hidden="true"
                            />
                            <span>Revise This Topic</span>
                          </Link>
                        </Button>

                        {rec.topic_id ? (
                          <TargetedPracticeButton
                            topicIds={[rec.topic_id]}
                            sourceAttemptId={attemptId}
                            label="Start Targeted Practice"
                            timerMode={
                              rec.action_type === "speed_drills"
                                ? "speed_challenge"
                                : "learning_mode"
                            }
                          />
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
