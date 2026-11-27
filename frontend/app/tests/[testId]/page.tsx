"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, Play } from "lucide-react";

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
import { startTestAttempt } from "@/lib/api/attempts";
import { formatTimerModeLabel, getTest, type TestOut } from "@/lib/api/tests";

export default function TestDetailPage() {
  const params = useParams<{ testId: string }>();
  const router = useRouter();
  const testId = params.testId;

  const [test, setTest] = React.useState<TestOut | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [isStarting, setIsStarting] = React.useState(false);

  React.useEffect(() => {
    if (!testId) return;
    const controller = new AbortController();
    getTest(testId, controller.signal)
      .then(setTest)
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to load test.",
        );
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  }, [testId]);

  const handleStart = async () => {
    if (!test) return;
    setIsStarting(true);
    setErrorMessage(null);
    try {
      const attempt = await startTestAttempt(test.id);
      router.push(`/attempts/${encodeURIComponent(attempt.attempt_id)}`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to start attempt.",
      );
      setIsStarting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="py-10 text-center text-sm text-muted-foreground">
        Loading test…
      </div>
    );
  }

  if (errorMessage || !test) {
    return (
      <div className="space-y-4">
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{errorMessage ?? "Test not found."}</span>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/tests">Back to Tests</Link>
        </Button>
      </div>
    );
  }

  const timerMode = String(test.settings_json.timer_mode ?? "speed_challenge");

  return (
    <div className="space-y-6">
      <PageHeader
        title={test.title}
        description={`Created ${new Date(test.created_at).toLocaleString()}`}
        actions={
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              disabled={isStarting}
              onClick={() => void handleStart()}
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              <span>{isStarting ? "Starting…" : "Start Attempt"}</span>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/tests">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>Back to Tests</span>
              </Link>
            </Button>
          </div>
        }
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>Test Settings</CardTitle>
            <Badge variant="secondary">{formatTimerModeLabel(timerMode)}</Badge>
          </div>
          <CardDescription>
            Questions are frozen as immutable snapshots for fair scoring.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs text-muted-foreground">Total Questions</dt>
              <dd className="mt-1 font-semibold">{test.total_questions}</dd>
            </div>
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs text-muted-foreground">Maximum Score</dt>
              <dd className="mt-1 font-semibold">{test.max_score}</dd>
            </div>
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs text-muted-foreground">Status</dt>
              <dd className="mt-1 font-semibold capitalize">{test.status}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
