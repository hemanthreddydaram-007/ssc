"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  ClipboardCheck,
  FileUp,
  Loader2,
  Play,
} from "lucide-react";

import { TargetedPracticeButton } from "@/components/analytics/TargetedPracticeButton";
import { HealthStatusCard } from "@/components/layout/HealthStatusCard";
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
import {
  getDashboardSummary,
  type DashboardSummaryOut,
} from "@/lib/api/dashboard";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import { formatTimerModeLabel } from "@/lib/api/tests";

export default function DashboardPage() {
  const [summary, setSummary] = React.useState<DashboardSummaryOut | null>(
    null,
  );
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setErrorMessage(null);
    getDashboardSummary(controller.signal)
      .then(setSummary)
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Unable to load dashboard summary.",
        );
      })
      .finally(() => setIsLoading(false));

    return () => controller.abort();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Your source-grounded study workspace, active jobs, recent tests, and weak topics."
        actions={
          <div className="flex flex-wrap items-center gap-2">
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
          </div>
        }
      />

      {errorMessage ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{errorMessage}</span>
        </div>
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
          </CardHeader>
          <CardContent className="space-y-2">
            {summary.active_jobs.map((job) => (
              <div
                key={job.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <Loader2
                    className="h-4 w-4 animate-spin text-primary"
                    aria-hidden="true"
                  />
                  <span className="font-medium capitalize">
                    {job.job_type.replace(/_/g, " ")} —{" "}
                    {job.current_stage.replace(/_/g, " ")}
                  </span>
                  <Badge variant="warning">{job.status}</Badge>
                </div>
                <Button asChild variant="outline" size="sm">
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
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Recent Uploads</CardTitle>
              <CardDescription>Latest study materials in your library.</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
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
                    <div className="min-w-0">
                      <Link
                        href={`/documents/${encodeURIComponent(doc.id)}`}
                        className="block truncate font-medium hover:text-primary hover:underline"
                      >
                        {doc.title}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {doc.page_count} pages · {doc.status}
                      </p>
                    </div>
                    <Button asChild variant="outline" size="sm">
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
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Recent Tests</CardTitle>
              <CardDescription>Latest completed and active attempts.</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/tests">View all</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {isLoading && !summary ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : !summary || summary.recent_attempts.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No tests attempted yet. Build a Speed Challenge or Learning Mode
                set.
              </p>
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
                      <div className="min-w-0">
                        <p className="truncate font-medium">
                          {attempt.test_title ?? "Practice Test"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {formatTimerModeLabel(attempt.timer_mode)}
                          {!isActive && attempt.total_score !== null
                            ? ` · Score ${attempt.total_score}/${attempt.max_score} · ${formatDurationMs(attempt.total_time_ms)}`
                            : " · In progress"}
                        </p>
                      </div>
                      <Button asChild variant="outline" size="sm">
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
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Weak Topics to Revise</CardTitle>
            <CardDescription>
              Topics with at least 5 attempted questions needing accuracy or
              speed practice.
            </CardDescription>
          </div>
          <Button asChild variant="ghost" size="sm">
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
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">
                        {topic.topic_name ?? "Topic"}
                      </span>
                      <Badge variant="outline">
                        {formatSubjectLabel(topic.subject_code)}
                      </Badge>
                      <Badge variant="destructive">
                        {topic.accuracy_percent.toFixed(1)}% accuracy
                      </Badge>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {topic.question_count} questions · Avg{" "}
                      {formatDurationMs(topic.average_time_ms)}
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

      <HealthStatusCard />
    </div>
  );
}
