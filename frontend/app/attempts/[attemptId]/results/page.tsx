"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  FileText,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";

import { ImprovementPlanPanel } from "@/components/analytics/ImprovementPlanPanel";
import { ObservationDiagnosisCard } from "@/components/analytics/ObservationDiagnosisCard";
import { ResultsSummaryCards } from "@/components/analytics/ResultsSummaryCards";
import { TopicBreakdownTable } from "@/components/analytics/TopicBreakdownTable";
import { RichMathText } from "@/components/common/MathRenderer";
import { PageHeader } from "@/components/layout/PageHeader";
import { SelfReportTagModal } from "@/components/test-player/SelfReportTagModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  formatDurationMs,
  getAttemptResults,
  getOptionKey,
  getOptionText,
  saveSelfReport,
  type AttemptResultsOut,
} from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import {
  generateImprovementPlan,
  getAttemptAnalysis,
  getImprovementPlan,
  type AttemptAnalysisOut,
  type ImprovementPlanOut,
} from "@/lib/api/performance";
import { formatTimerModeLabel } from "@/lib/api/tests";
import { cn } from "@/lib/utils/cn";

export default function AttemptResultsPage() {
  const params = useParams<{ attemptId: string }>();
  const attemptId = params.attemptId;

  const [results, setResults] = React.useState<AttemptResultsOut | null>(null);
  const [analysis, setAnalysis] = React.useState<AttemptAnalysisOut | null>(
    null,
  );
  const [plan, setPlan] = React.useState<ImprovementPlanOut | null>(null);

  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [planLoading, setPlanLoading] = React.useState(false);
  const [planGenerating, setPlanGenerating] = React.useState(false);
  const [planError, setPlanError] = React.useState<string | null>(null);
  const [savingResponseId, setSavingResponseId] = React.useState<string | null>(
    null,
  );

  React.useEffect(() => {
    if (!attemptId) return;
    const controller = new AbortController();
    setIsLoading(true);
    setPlanLoading(true);
    setErrorMessage(null);

    getAttemptResults(attemptId, controller.signal)
      .then((loadedResults) => {
        setResults(loadedResults);
        void getAttemptAnalysis(attemptId, controller.signal)
          .then(setAnalysis)
          .catch(() => undefined);

        void getImprovementPlan(attemptId, controller.signal)
          .then(setPlan)
          .catch((err) => {
            if (err instanceof ApiError && err.status === 404) {
              setPlan(null);
            }
          })
          .finally(() => setPlanLoading(false));
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load attempt results.",
        );
        setPlanLoading(false);
      })
      .finally(() => setIsLoading(false));

    return () => controller.abort();
  }, [attemptId]);

  const handleGeneratePlan = async (forceRegenerate: boolean) => {
    if (!attemptId) return;
    setPlanGenerating(true);
    setPlanError(null);
    try {
      const generated = await generateImprovementPlan(attemptId, {
        include_ai_coaching: true,
        force_regenerate: forceRegenerate,
      });
      setPlan(generated);
    } catch (error) {
      setPlanError(
        error instanceof Error
          ? error.message
          : "Failed to generate improvement plan.",
      );
    } finally {
      setPlanGenerating(false);
    }
  };

  const handleSaveSelfReport = async (
    responseId: string,
    reason: string | null,
  ) => {
    if (!results) return;
    setSavingResponseId(responseId);
    try {
      await saveSelfReport(results.attempt_id, responseId, {
        mistake_reason_self_report: reason,
      });
      setResults((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          questions: prev.questions.map((q) =>
            q.response_id === responseId
              ? { ...q, mistake_reason_self_report: reason }
              : q,
          ),
        };
      });
      // Refresh analysis so updated self-report tags refine tentative error categories
      const refreshedAnalysis = await getAttemptAnalysis(results.attempt_id).catch(
        () => null,
      );
      if (refreshedAnalysis) {
        setAnalysis(refreshedAnalysis);
      }
    } finally {
      setSavingResponseId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Results Report"
          description="Loading graded attempt results…"
        />
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Calculating score, error signals, and topic breakdown…
          </CardContent>
        </Card>
      </div>
    );
  }

  if (errorMessage || !results) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Results Unavailable"
          description="Unable to load results for this attempt."
          actions={
            <Button asChild variant="outline" size="sm">
              <Link href="/tests">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>Back to Tests</span>
              </Link>
            </Button>
          }
        />
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{errorMessage ?? "Results not found."}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={results.test_title ?? "Test Results"}
        description={`${formatTimerModeLabel(results.timer_mode)} · Submitted ${results.submitted_at ? new Date(results.submitted_at).toLocaleString() : "recently"}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href="/performance">Performance Trends</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href={`/tests/${encodeURIComponent(results.test_id)}`}>
                Retake Test
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/tests">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>All Tests</span>
              </Link>
            </Button>
          </div>
        }
      />

      <ResultsSummaryCards results={results} />

      <TopicBreakdownTable
        topics={results.topic_breakdown}
        difficulties={results.difficulty_breakdown}
      />

      {analysis && analysis.comparison_to_previous.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Change vs. Previous Attempts</CardTitle>
            <CardDescription>
              Topic accuracy and speed compared against your prior graded
              attempt on each topic.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {analysis.comparison_to_previous.map((cmp) => {
                const accImproved =
                  cmp.accuracy_delta !== null && cmp.accuracy_delta > 0;
                const accDeclined =
                  cmp.accuracy_delta !== null && cmp.accuracy_delta < 0;
                return (
                  <div
                    key={cmp.topic_id}
                    className="rounded-md border bg-muted/30 p-3 text-sm"
                  >
                    <p className="font-semibold">{cmp.topic_name}</p>
                    <div className="mt-1 flex items-center gap-2 text-xs">
                      <span>{cmp.current_accuracy_percent.toFixed(1)}%</span>
                      {cmp.accuracy_delta !== null ? (
                        <span
                          className={cn(
                            "inline-flex items-center gap-0.5 font-medium",
                            accImproved
                              ? "text-emerald-700"
                              : accDeclined
                                ? "text-red-700"
                                : "text-muted-foreground",
                          )}
                        >
                          {accImproved ? (
                            <TrendingUp className="h-3 w-3" aria-hidden="true" />
                          ) : accDeclined ? (
                            <TrendingDown
                              className="h-3 w-3"
                              aria-hidden="true"
                            />
                          ) : null}
                          {cmp.accuracy_delta > 0 ? "+" : ""}
                          {cmp.accuracy_delta.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-muted-foreground">
                          First attempt
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Avg time: {formatDurationMs(cmp.current_avg_time_ms)}
                    </p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {analysis ? <ObservationDiagnosisCard analysis={analysis} /> : null}

      <ImprovementPlanPanel
        attemptId={results.attempt_id}
        plan={plan}
        isLoading={planLoading}
        isGenerating={planGenerating}
        errorMessage={planError}
        onGenerate={(force) => void handleGeneratePlan(force)}
      />

      {/* Full Question Review */}
      <Card>
        <CardHeader>
          <CardTitle>Question-by-Question Review</CardTitle>
          <CardDescription>
            Review your selected option, server-verified answer, explanation,
            and optional mistake reflection tags.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {results.questions.map((q) => {
            const isCorrect = q.is_correct === true;
            const isWrong = q.is_correct === false;

            return (
              <div
                key={q.test_question_id}
                className="rounded-lg border p-4 space-y-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-semibold">
                      Q{q.display_order}
                    </span>
                    <Badge variant="outline">
                      {formatSubjectLabel(q.subject_code)}
                    </Badge>
                    {q.topic_name ? (
                      <Badge variant="outline">{q.topic_name}</Badge>
                    ) : null}
                    <Badge
                      variant={
                        isCorrect
                          ? "success"
                          : isWrong
                            ? "destructive"
                            : "warning"
                      }
                    >
                      {q.status.replace(/_/g, " ")}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                      {formatDurationMs(q.time_spent_ms)}
                    </span>
                    {q.graded_points !== null ? (
                      <span className="font-medium text-foreground">
                        {Number(q.graded_points) > 0
                          ? `+${q.graded_points}`
                          : q.graded_points}{" "}
                        pts
                      </span>
                    ) : null}
                  </div>
                </div>

                <div className="text-sm font-medium">
                  <RichMathText text={q.question_text} />
                </div>

                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {q.options.map((opt) => {
                    const optKey = getOptionKey(opt);
                    const optText = getOptionText(opt);
                    const isSelected = q.selected_option_key === optKey;
                    const isAnswer = q.correct_option_key === optKey;
                    return (
                      <div
                        key={optKey}
                        className={cn(
                          "flex items-start justify-between gap-2 rounded-md border px-3 py-2 text-xs",
                          isAnswer
                            ? "border-emerald-300 bg-emerald-50/70"
                            : isSelected && !isAnswer
                              ? "border-red-300 bg-red-50/70"
                              : "bg-muted/20",
                        )}
                      >
                        <div className="flex items-start gap-2">
                          <span className="font-semibold">({optKey})</span>
                          <RichMathText text={optText} />
                        </div>
                        {isAnswer ? (
                          <CheckCircle2
                            className="h-4 w-4 shrink-0 text-emerald-600"
                            aria-hidden="true"
                          />
                        ) : isSelected ? (
                          <XCircle
                            className="h-4 w-4 shrink-0 text-red-600"
                            aria-hidden="true"
                          />
                        ) : null}
                      </div>
                    );
                  })}
                </div>

                {q.explanation ? (
                  <div className="rounded-md border bg-muted/30 p-3 text-xs">
                    <p className="mb-1 font-semibold text-foreground">
                      Explanation
                    </p>
                    <RichMathText text={q.explanation} />
                  </div>
                ) : null}

                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  {q.source_document_id ? (
                    <Link
                      href={`/documents/${encodeURIComponent(q.source_document_id)}${q.source_page_number ? `?tab=source_pages&page=${q.source_page_number}` : ""}`}
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>
                        Source document
                        {q.source_page_number
                          ? ` (Page ${q.source_page_number})`
                          : ""}
                      </span>
                    </Link>
                  ) : (
                    <span />
                  )}

                  {!isCorrect ? (
                    <SelfReportTagModal
                      currentReason={q.mistake_reason_self_report}
                      isSaving={savingResponseId === q.response_id}
                      onSave={(reason) =>
                        handleSaveSelfReport(q.response_id, reason)
                      }
                    />
                  ) : null}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
