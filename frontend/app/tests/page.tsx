"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, ClipboardCheck, Play, Plus } from "lucide-react";

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
import {
  formatDurationMs,
  listAttempts,
  startTestAttempt,
  type AttemptSummaryOut,
} from "@/lib/api/attempts";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import {
  formatTimerModeLabel,
  listTests,
  type TestOut,
} from "@/lib/api/tests";

function TestsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [tests, setTests] = React.useState<TestOut[]>([]);
  const [attempts, setAttempts] = React.useState<AttemptSummaryOut[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [startingTestId, setStartingTestId] = React.useState<string | null>(
    null,
  );

  // If navigated from Question Bank with preselected filters/question_ids, forward cleanly to /tests/new
  React.useEffect(() => {
    const qIds = searchParams.get("question_ids");
    const docId = searchParams.get("document_id");
    const subCode = searchParams.get("subject_code");
    const topId = searchParams.get("topic_id");
    if (qIds || docId || subCode || topId) {
      router.replace(`/tests/new?${searchParams.toString()}`);
    }
  }, [searchParams, router]);

  const loadAll = React.useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [testsRes, attemptsRes] = await Promise.all([
        listTests({ limit: 30 }, signal),
        listAttempts({ limit: 30 }, signal),
      ]);
      setTests(testsRes.items);
      setAttempts(attemptsRes.items);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load tests.",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    const controller = new AbortController();
    void loadAll(controller.signal);
    return () => controller.abort();
  }, [loadAll]);

  const handleStartTest = async (testId: string) => {
    setStartingTestId(testId);
    setErrorMessage(null);
    try {
      const started = await startTestAttempt(testId);
      router.push(`/attempts/${encodeURIComponent(started.attempt_id)}`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to start test.",
      );
      setStartingTestId(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tests"
        description="Build custom timed tests or resume in-progress attempts."
        actions={
          <Button asChild size="sm">
            <Link href="/tests/new">
              <Plus className="h-4 w-4" aria-hidden="true" />
              <span>Create Test</span>
            </Link>
          </Button>
        }
      />

      {errorMessage ? (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {errorMessage}
        </div>
      ) : null}

      {/* Recent & Active Attempts */}
      <Card>
        <CardHeader>
          <CardTitle>Recent &amp; In-Progress Attempts</CardTitle>
          <CardDescription>
            Resume active attempts or open graded result reports.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && attempts.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Loading attempts…
            </p>
          ) : attempts.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No test attempts yet. Create or start a test below.
            </p>
          ) : (
            <div className="space-y-2.5">
              {attempts.map((attempt) => {
                const isActive = attempt.status === "in_progress";
                return (
                  <div
                    key={attempt.id}
                    className="flex flex-col gap-3 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">
                          {attempt.test_title ?? "Test Attempt"}
                        </span>
                        <Badge variant="outline">
                          {formatTimerModeLabel(attempt.timer_mode)}
                        </Badge>
                        <Badge variant={isActive ? "warning" : "success"}>
                          {attempt.status.replace(/_/g, " ")}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Started {new Date(attempt.started_at).toLocaleString()}
                        {!isActive && attempt.total_score !== null
                          ? ` · Score ${attempt.total_score}/${attempt.max_score} · ${formatDurationMs(attempt.total_time_ms)}`
                          : ""}
                      </p>
                    </div>
                    <Button asChild size="sm" variant={isActive ? "default" : "outline"}>
                      <Link
                        href={
                          isActive
                            ? `/attempts/${encodeURIComponent(attempt.id)}`
                            : `/attempts/${encodeURIComponent(attempt.id)}/results`
                        }
                      >
                        <span>{isActive ? "Resume Test" : "View Results"}</span>
                        <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                      </Link>
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Created Tests */}
      <Card>
        <CardHeader>
          <CardTitle>Saved Tests</CardTitle>
          <CardDescription>
            Launch a fresh timed attempt on any configured test.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && tests.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Loading tests…
            </p>
          ) : tests.length === 0 ? (
            <div className="rounded-md border border-dashed py-10 text-center">
              <ClipboardCheck
                className="mx-auto h-8 w-8 text-muted-foreground"
                aria-hidden="true"
              />
              <p className="mt-2 text-sm font-medium">No tests created yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Use the Test Builder to create a Speed Challenge, Exam
                Simulation, or Learning Mode set.
              </p>
              <Button asChild size="sm" className="mt-4">
                <Link href="/tests/new">Build First Test</Link>
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {tests.map((test) => (
                <div
                  key={test.id}
                  className="flex flex-col justify-between rounded-lg border p-4"
                >
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant="secondary">
                        {test.total_questions} questions
                      </Badge>
                      <Badge variant="outline">Max {test.max_score} pts</Badge>
                      {test.subject_code ? (
                        <Badge variant="outline">
                          {formatSubjectLabel(test.subject_code)}
                        </Badge>
                      ) : null}
                    </div>
                    <h3 className="font-semibold">
                      <Link
                        href={`/tests/${encodeURIComponent(test.id)}`}
                        className="hover:text-primary hover:underline"
                      >
                        {test.title}
                      </Link>
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Created {new Date(test.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="mt-4 flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      disabled={startingTestId === test.id}
                      onClick={() => void handleStartTest(test.id)}
                    >
                      <Play className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>
                        {startingTestId === test.id
                          ? "Starting…"
                          : "Start Attempt"}
                      </span>
                    </Button>
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/tests/${encodeURIComponent(test.id)}`}>
                        Details
                      </Link>
                    </Button>
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

export default function TestsPage() {
  return (
    <React.Suspense
      fallback={
        <div className="py-10 text-center text-sm text-muted-foreground">
          Loading tests…
        </div>
      }
    >
      <TestsContent />
    </React.Suspense>
  );
}
