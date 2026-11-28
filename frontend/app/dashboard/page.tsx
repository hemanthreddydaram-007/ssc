"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  FileUp,
  HelpCircle,
  Loader2,
  Play,
  RefreshCw,
  X,
} from "lucide-react";

import { TargetedPracticeButton } from "@/components/analytics/TargetedPracticeButton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDurationMs, getAttemptId } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import {
  getDashboardSummary,
  type DashboardSummaryOut,
} from "@/lib/api/dashboard";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import {
  formatJobStageLabel,
  formatJobTypeTitle,
  type ProcessingJobOut,
} from "@/lib/api/jobs";
import { formatTimerModeLabel } from "@/lib/api/tests";
import { cn } from "@/lib/utils/cn";
import {
  formatDecimal,
  formatPercent,
  toNumber,
} from "@/lib/utils/number";

const QUICKSTART_DISMISSED_KEY = "ai_exam_coach_hide_quickstart_v1";

function getJobDocumentTitle(job: ProcessingJobOut): string {
  return job.document_title && job.document_title.trim().length > 0
    ? job.document_title
    : "Uploaded Document";
}

interface WorkflowStep {
  stepNumber: number;
  title: string;
  description: string;
  done: boolean;
  href: string;
  actionLabel: string;
  icon: React.ComponentType<{ className?: string }>;
}

function buildWorkflowSteps(summary: DashboardSummaryOut | null): {
  steps: WorkflowStep[];
  nextStepNumber: number;
} {
  const docsCount = summary?.totals.documents_count ?? 0;
  const notesCount = summary?.totals.notes_count ?? 0;
  const questionsCount = summary?.totals.questions_count ?? 0;
  const attemptsCount = summary?.totals.completed_attempts_count ?? 0;
  const latestDocId = summary?.recent_documents[0]?.id;

  const hasDocs = docsCount > 0;
  const hasNotes = notesCount > 0;
  const hasStartedOrDoneTest =
    attemptsCount > 0 || Boolean(summary?.continue_attempt);
  const hasCompletedTest = attemptsCount > 0;

  const notesHref =
    hasDocs && !hasNotes && latestDocId
      ? `/documents/${encodeURIComponent(latestDocId)}`
      : "/notes";

  const testHref = summary?.continue_attempt
    ? `/attempts/${encodeURIComponent(getAttemptId(summary.continue_attempt))}`
    : hasDocs && questionsCount === 0 && latestDocId
      ? `/documents/${encodeURIComponent(latestDocId)}`
      : "/tests/new";

  const steps: WorkflowStep[] = [
    {
      stepNumber: 1,
      title: "Upload Material",
      description: hasDocs
        ? `${docsCount} ${docsCount === 1 ? "document" : "documents"} in your library.`
        : "Add a PDF, previous-year paper, image, or pasted notes.",
      done: hasDocs,
      href: "/library",
      actionLabel: "Upload PDF",
      icon: FileUp,
    },
    {
      stepNumber: 2,
      title: "Generate Smart Notes",
      description: hasNotes
        ? `${notesCount} ${notesCount === 1 ? "note" : "notes"} ready to revise.`
        : hasDocs
          ? "Open your document to extract concepts & smart notes."
          : "Turn extracted pages into detailed & quick-revision notes.",
      done: hasNotes,
      href: notesHref,
      actionLabel: "Generate Notes",
      icon: BookOpen,
    },
    {
      stepNumber: 3,
      title: "Take Timed Practice Test",
      description: hasCompletedTest
        ? `${attemptsCount} ${attemptsCount === 1 ? "test" : "tests"} completed.`
        : summary?.continue_attempt
          ? "You have an in-progress test ready to resume."
          : "Build a Speed Challenge, Exam Simulation, or Learning Mode set.",
      done: hasStartedOrDoneTest,
      href: testHref,
      actionLabel: summary?.continue_attempt ? "Resume Test" : "Create Test",
      icon: ClipboardCheck,
    },
    {
      stepNumber: 4,
      title: "Fix Weak Topics",
      description: hasCompletedTest
        ? "Inspect accuracy vs speed diagnostics and targeted practice."
        : "Complete a test to unlock topic diagnostics & revision queues.",
      done: false,
      href: "/performance",
      actionLabel: "Review Weak Topics",
      icon: BarChart3,
    },
  ];

  let nextStepNumber = 1;
  if (!hasDocs) {
    nextStepNumber = 1;
  } else if (!hasNotes) {
    nextStepNumber = 2;
  } else if (!hasCompletedTest) {
    nextStepNumber = 3;
  } else {
    nextStepNumber = 4;
  }

  return { steps, nextStepNumber };
}

export default function DashboardPage() {
  const [summary, setSummary] = React.useState<DashboardSummaryOut | null>(
    null,
  );
  const [isLoading, setIsLoading] = React.useState(true);
  const [isRedirecting, setIsRedirecting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [isNetworkError, setIsNetworkError] = React.useState(false);
  const [quickStartHidden, setQuickStartHidden] = React.useState(false);
  const activeAbortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    try {
      setQuickStartHidden(
        window.localStorage.getItem(QUICKSTART_DISMISSED_KEY) === "1",
      );
    } catch {
      // Ignore storage errors
    }
  }, []);

  const loadSummary = React.useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setErrorMessage(null);
    setIsNetworkError(false);
    try {
      const data = await getDashboardSummary(signal);
      setSummary(data);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      if (error instanceof ApiError && error.status === 401) {
        setIsRedirecting(true);
        return;
      }
      if (
        error instanceof TypeError ||
        (error instanceof ApiError && error.status >= 502)
      ) {
        setIsNetworkError(true);
        setErrorMessage(
          "Unable to reach the server right now. On free hosting it may be waking up (~30–50s) — wait a moment and click Retry.",
        );
      } else {
        setIsNetworkError(false);
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Unable to load dashboard summary.",
        );
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    const controller = new AbortController();
    activeAbortRef.current = controller;
    void loadSummary(controller.signal);
    return () => {
      controller.abort();
    };
  }, [loadSummary]);

  const handleRetry = () => {
    activeAbortRef.current?.abort();
    const controller = new AbortController();
    activeAbortRef.current = controller;
    void loadSummary(controller.signal);
  };

  const handleToggleQuickStart = (hide: boolean) => {
    setQuickStartHidden(hide);
    try {
      if (hide) {
        window.localStorage.setItem(QUICKSTART_DISMISSED_KEY, "1");
      } else {
        window.localStorage.removeItem(QUICKSTART_DISMISSED_KEY);
      }
    } catch {
      // Ignore storage errors
    }
  };

  const { steps: workflowSteps, nextStepNumber } = React.useMemo(
    () => buildWorkflowSteps(summary),
    [summary],
  );

  if (isRedirecting) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        Redirecting to sign in…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Your source-grounded study workspace, active jobs, recent tests, and weak topics."
        actions={
          <>
            {quickStartHidden ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => handleToggleQuickStart(false)}
              >
                <HelpCircle className="h-4 w-4" aria-hidden="true" />
                <span>Show Study Guide</span>
              </Button>
            ) : null}
            <Button asChild size="sm">
              <Link href="/library">
                <FileUp className="h-4 w-4" aria-hidden="true" />
                <span>Upload Material</span>
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/notes">
                <BookOpen className="h-4 w-4" aria-hidden="true" />
                <span>Smart Notes</span>
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/tests/new">
                <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
                <span>Create Test</span>
              </Link>
            </Button>
          </>
        }
      />

      {errorMessage ? (
        <div
          role="alert"
          className={cn(
            "flex flex-wrap items-center justify-between gap-3 rounded-md border p-4 text-sm",
            isNetworkError
              ? "border-amber-200 bg-amber-50 text-amber-900"
              : "border-red-200 bg-red-50 text-red-800",
          )}
        >
          <div className="flex items-start gap-2">
            <AlertCircle
              className="mt-0.5 h-4 w-4 shrink-0"
              aria-hidden="true"
            />
            <span>{errorMessage}</span>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRetry}
            disabled={isLoading}
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", isLoading && "animate-spin")}
              aria-hidden="true"
            />
            <span>{isLoading ? "Retrying…" : "Retry"}</span>
          </Button>
        </div>
      ) : null}

      {/* Smart 4-Step Study Workflow Guide */}
      {!quickStartHidden ? (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 pb-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle>Your Study Workflow (Quick Start)</CardTitle>
                <Badge variant="secondary">
                  Next: Step {nextStepNumber}
                </Badge>
              </div>
              <CardDescription className="mt-1">
                Follow these 4 steps to turn your PDFs into notes, timed tests,
                and targeted score gains.
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0"
              aria-label="Dismiss study workflow guide"
              onClick={() => handleToggleQuickStart(true)}
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Button>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {workflowSteps.map((step) => {
                const Icon = step.icon;
                const isNext = step.stepNumber === nextStepNumber;
                return (
                  <div
                    key={step.stepNumber}
                    className={cn(
                      "flex flex-col justify-between gap-3 rounded-md border p-3.5",
                      isNext
                        ? "border-primary/50 bg-primary/5"
                        : "bg-card",
                    )}
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                          <Icon className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                          <span>Step {step.stepNumber}</span>
                        </span>
                        {step.done ? (
                          <Badge variant="success" className="gap-1">
                            <CheckCircle2
                              className="h-3 w-3"
                              aria-hidden="true"
                            />
                            <span>Done</span>
                          </Badge>
                        ) : isNext ? (
                          <Badge variant="default">Recommended</Badge>
                        ) : null}
                      </div>
                      <p className="mt-2 text-sm font-semibold">{step.title}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {step.description}
                      </p>
                    </div>
                    <Button
                      asChild
                      size="sm"
                      variant={isNext ? "default" : "outline"}
                      className="w-full"
                    >
                      <Link href={step.href}>
                        <span>{step.actionLabel}</span>
                        <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                      </Link>
                    </Button>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Continue Learning Banner */}
      {summary?.continue_attempt ? (
        <Card className="border-primary/40 bg-primary/5">
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Continue In-Progress Test</CardTitle>
              <CardDescription>
                {summary.continue_attempt.test_title ?? "Active Attempt"} ·{" "}
                {formatTimerModeLabel(summary.continue_attempt.timer_mode)} ·
                Started{" "}
                {new Date(summary.continue_attempt.started_at).toLocaleString()}
              </CardDescription>
            </div>
            <Button asChild size="sm">
              <Link
                href={`/attempts/${encodeURIComponent(getAttemptId(summary.continue_attempt))}`}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                <span>Resume Test</span>
              </Link>
            </Button>
          </CardHeader>
        </Card>
      ) : null}

      {/* Real Workspace Totals */}
      {summary ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Documents</CardDescription>
              <CardTitle className="text-2xl">
                {summary.totals.documents_count}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Smart Notes</CardDescription>
              <CardTitle className="text-2xl">
                {summary.totals.notes_count}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Question Bank</CardDescription>
              <CardTitle className="text-2xl">
                {summary.totals.questions_count}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Completed Tests</CardDescription>
              <CardTitle className="text-2xl">
                {summary.totals.completed_attempts_count}
              </CardTitle>
            </CardHeader>
          </Card>
        </div>
      ) : null}

      {/* Active Processing Jobs */}
      {summary && summary.active_jobs.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Active Processing Jobs</CardTitle>
            <CardDescription>
              Live extraction and AI generation tasks currently running in your
              workspace.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {summary.active_jobs.map((job) => (
              <div
                key={job.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm"
              >
                <div className="flex min-w-0 flex-1 items-start gap-2.5">
                  <Loader2
                    className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary"
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-medium">
                        {getJobDocumentTitle(job)}
                      </span>
                      <Badge variant="warning">{job.status}</Badge>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {formatJobTypeTitle(job.job_type)} ·{" "}
                      {formatJobStageLabel(job.current_stage)}
                      {job.progress_percent !== null
                        ? ` (${job.progress_percent}%)`
                        : ""}
                    </p>
                  </div>
                </div>
                <Button asChild variant="outline" size="sm" className="shrink-0">
                  <Link href={`/documents/${encodeURIComponent(job.document_id)}`}>
                    View Status
                  </Link>
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent Uploads */}
        <Card className="min-w-0">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div className="min-w-0">
              <CardTitle>Recent Uploads</CardTitle>
              <CardDescription>
                Latest study materials in your library.
              </CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm" className="shrink-0">
              <Link href="/library">View all</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {isLoading && !summary ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : !summary || summary.recent_documents.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No documents uploaded yet. Upload a PDF, image, or pasted text
                to begin.
              </p>
            ) : (
              <div className="space-y-2.5">
                {summary.recent_documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between gap-2 rounded-md border p-3 text-sm"
                  >
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/documents/${encodeURIComponent(doc.id)}`}
                        className="block truncate font-medium hover:text-primary hover:underline"
                      >
                        {doc.title}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {doc.page_count}{" "}
                        {doc.page_count === 1 ? "page" : "pages"} ·{" "}
                        {doc.status.replace(/_/g, " ")}
                      </p>
                    </div>
                    <Button asChild variant="outline" size="sm" className="shrink-0">
                      <Link href={`/documents/${encodeURIComponent(doc.id)}`}>
                        Open
                      </Link>
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Tests */}
        <Card className="min-w-0">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div className="min-w-0">
              <CardTitle>Recent Tests</CardTitle>
              <CardDescription>
                Latest completed test attempts.
              </CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm" className="shrink-0">
              <Link href="/tests">View all</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {isLoading && !summary ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : !summary || summary.recent_attempts.length === 0 ? (
              summary?.continue_attempt ? (
                <p className="text-sm text-muted-foreground">
                  No completed tests yet — finish or resume your active attempt
                  above.
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No tests attempted yet. Build a Speed Challenge or Learning
                  Mode set.
                </p>
              )
            ) : (
              <div className="space-y-2.5">
                {summary.recent_attempts.map((attempt) => {
                  const attemptId = getAttemptId(attempt);
                  const isActive = attempt.status === "in_progress";
                  return (
                    <div
                      key={attemptId}
                      className="flex items-center justify-between gap-2 rounded-md border p-3 text-sm"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">
                          {attempt.test_title ?? "Practice Test"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {formatTimerModeLabel(attempt.timer_mode)}
                          {!isActive && attempt.total_score !== null
                            ? ` · Score ${formatDecimal(attempt.total_score)}/${formatDecimal(attempt.max_score)} · ${formatDurationMs(attempt.total_time_ms)}`
                            : " · In progress"}
                        </p>
                      </div>
                      <Button asChild variant="outline" size="sm" className="shrink-0">
                        <Link
                          href={
                            isActive
                              ? `/attempts/${encodeURIComponent(attemptId)}`
                              : `/attempts/${encodeURIComponent(attemptId)}/results`
                          }
                        >
                          <span>{isActive ? "Resume" : "Results"}</span>
                          <ArrowRight
                            className="h-3.5 w-3.5"
                            aria-hidden="true"
                          />
                        </Link>
                      </Button>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Weak Topics to Revise */}
      <Card className="min-w-0">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div className="min-w-0">
            <CardTitle>Weak Topics to Revise</CardTitle>
            <CardDescription>
              Topics with at least 5 attempted questions needing accuracy or
              speed practice.
            </CardDescription>
          </div>
          <Button asChild variant="ghost" size="sm" className="shrink-0">
            <Link href="/performance">Full Performance</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {!summary || summary.weak_topics.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No weak topics flagged yet (topics require at least 5 attempted
              questions before classifying).
            </p>
          ) : (
            <div className="space-y-3">
              {summary.weak_topics.map((topic) => (
                <div
                  key={topic.topic_id}
                  className="flex flex-col gap-3 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">
                        {topic.topic_name ?? "Topic"}
                      </span>
                      <Badge variant="outline">
                        {formatSubjectLabel(topic.subject_code)}
                      </Badge>
                      <Badge variant="destructive">
                        {formatPercent(topic.accuracy_percent, 1)} accuracy
                      </Badge>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {topic.question_count}{" "}
                      {topic.question_count === 1 ? "question" : "questions"} ·
                      Avg {formatDurationMs(toNumber(topic.average_time_ms, 0))}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button asChild variant="outline" size="sm">
                      <Link
                        href={`/notes?topic_id=${encodeURIComponent(topic.topic_id)}`}
                      >
                        <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>Revise Notes</span>
                      </Link>
                    </Button>
                    <TargetedPracticeButton
                      topicIds={[topic.topic_id]}
                      label="Practise"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
