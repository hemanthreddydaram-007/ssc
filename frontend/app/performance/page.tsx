"use client";

import * as React from "react";
import Link from "next/link";
import { AlertCircle, BarChart3, TrendingDown, TrendingUp } from "lucide-react";

import { PerformanceTrendsChart } from "@/components/analytics/PerformanceTrendsChart";
import { RevisionQueueCard } from "@/components/analytics/RevisionQueueCard";
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
import { formatDurationMs } from "@/lib/api/attempts";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import {
  getPerformanceOverview,
  getTopicTrends,
  updateRevisionStatus,
  type PerformanceOverviewOut,
  type TopicPerformanceOut,
  type TopicTrendsOut,
} from "@/lib/api/performance";
import { cn } from "@/lib/utils/cn";
import {
  formatPercent,
  toNullableNumber,
  toNumber,
} from "@/lib/utils/number";

function TopicBucketCard({
  title,
  description,
  topics,
  badgeVariant,
  selectedTopicId,
  onSelectTopic,
}: {
  title: string;
  description: string;
  topics: readonly TopicPerformanceOut[];
  badgeVariant: "success" | "destructive" | "warning" | "secondary";
  selectedTopicId: string | null;
  onSelectTopic: (topicId: string) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">{title}</CardTitle>
          <Badge variant={badgeVariant}>{topics.length}</Badge>
        </div>
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {topics.length === 0 ? (
          <p className="text-xs text-muted-foreground">No topics in this category.</p>
        ) : (
          <div className="space-y-2">
            {topics.map((t) => {
              const isSelected = selectedTopicId === t.topic_id;
              const acc = toNumber(t.accuracy_percent, 0);
              const prevAcc = toNullableNumber(t.previous_accuracy_percent);
              const explicitDelta = toNullableNumber(t.accuracy_delta_percent);
              const delta =
                explicitDelta ?? (prevAcc !== null ? acc - prevAcc : null);
              return (
                <button
                  key={t.topic_id}
                  type="button"
                  onClick={() => onSelectTopic(t.topic_id)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-md border p-2.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    isSelected
                      ? "border-primary bg-primary/5 ring-1 ring-primary"
                      : "hover:bg-muted/40",
                  )}
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-foreground">
                      {t.topic_name ?? "Topic"}
                    </p>
                    <p className="mt-0.5 text-muted-foreground">
                      {formatSubjectLabel(t.subject_code)} · {t.question_count}{" "}
                      {t.question_count === 1 ? "question" : "questions"}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-semibold">
                      {formatPercent(t.accuracy_percent, 1, "0.0%")}
                    </p>
                    <p className="text-muted-foreground">
                      {formatDurationMs(t.average_time_ms)}
                      {delta !== null ? (
                        <span
                          className={cn(
                            "ml-1 inline-flex items-center",
                            delta > 0
                              ? "text-emerald-700"
                              : delta < 0
                                ? "text-red-700"
                                : "",
                          )}
                        >
                          {delta > 0 ? (
                            <TrendingUp className="h-3 w-3" aria-hidden="true" />
                          ) : delta < 0 ? (
                            <TrendingDown
                              className="h-3 w-3"
                              aria-hidden="true"
                            />
                          ) : null}
                          {delta > 0 ? "+" : ""}
                          {delta.toFixed(1)}%
                        </span>
                      ) : null}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function PerformanceDashboardPage() {
  const [overview, setOverview] = React.useState<PerformanceOverviewOut | null>(
    null,
  );
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const [selectedTopicId, setSelectedTopicId] = React.useState<string | null>(
    null,
  );
  const [trends, setTrends] = React.useState<TopicTrendsOut | null>(null);
  const [trendsLoading, setTrendsLoading] = React.useState(false);
  const [trendsError, setTrendsError] = React.useState<string | null>(null);

  const loadOverview = React.useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await getPerformanceOverview(signal);
      setOverview(data);
      const firstTopic =
        data.weak_topics[0] ??
        data.developing_topics[0] ??
        data.strong_topics[0] ??
        data.insufficient_data_topics[0];
      if (firstTopic) {
        setSelectedTopicId((prev) => prev ?? firstTopic.topic_id);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to load performance dashboard.",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    const controller = new AbortController();
    void loadOverview(controller.signal);
    return () => controller.abort();
  }, [loadOverview]);

  React.useEffect(() => {
    if (!selectedTopicId) {
      setTrends(null);
      return;
    }
    const controller = new AbortController();
    setTrendsLoading(true);
    setTrendsError(null);
    getTopicTrends(selectedTopicId, controller.signal)
      .then(setTrends)
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setTrendsError(
          error instanceof Error
            ? error.message
            : "Failed to load topic trends.",
        );
      })
      .finally(() => setTrendsLoading(false));

    return () => controller.abort();
  }, [selectedTopicId]);

  const handleRevisionStatus = async (
    itemId: string,
    status: "completed" | "dismissed",
  ) => {
    await updateRevisionStatus(itemId, status);
    await loadOverview();
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Performance"
        description="Cross-attempt topic accuracy, solving speed trends, and targeted revision queues."
        actions={
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void loadOverview()}
              disabled={isLoading}
            >
              Refresh
            </Button>
            <Button asChild size="sm">
              <Link href="/tests/new">New Practice Test</Link>
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

      {isLoading && !overview ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Loading cross-attempt analytics…
          </CardContent>
        </Card>
      ) : overview && overview.total_attempts === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <BarChart3
              className="mx-auto h-9 w-9 text-muted-foreground"
              aria-hidden="true"
            />
            <p className="mt-3 text-sm font-medium">
              No completed attempts yet
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Complete a timed test to unlock topic accuracy trends, speed
              diagnostics, and targeted practice recommendations.
            </p>
            <Button asChild size="sm" className="mt-4">
              <Link href="/tests/new">Start First Test</Link>
            </Button>
          </CardContent>
        </Card>
      ) : overview ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Completed Attempts</CardDescription>
                <CardTitle className="text-2xl">
                  {overview.total_attempts}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Overall Accuracy</CardDescription>
                <CardTitle className="text-2xl">
                  {formatPercent(overview.overall_accuracy_percent, 1, "—")}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Overall Avg Time / Question</CardDescription>
                <CardTitle className="text-2xl">
                  {formatDurationMs(overview.overall_avg_time_ms)}
                </CardTitle>
              </CardHeader>
            </Card>
          </div>

          {overview.weak_topics.length > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4">
              <div>
                <p className="text-sm font-semibold text-amber-950">
                  {overview.weak_topics.length}{" "}
                  {overview.weak_topics.length === 1 ? "topic" : "topics"} need
                  focused practice
                </p>
                <p className="text-xs text-amber-900/80">
                  Start an easy-to-medium targeted drill across your weak
                  topics.
                </p>
              </div>
              <TargetedPracticeButton
                topicIds={overview.weak_topics.map((t) => t.topic_id)}
                label="Practise All Weak Topics"
              />
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            <TopicBucketCard
              title="Needs Practice"
              description="Topics with >=5 questions and accuracy below 50% (or flagged weak)."
              topics={overview.weak_topics}
              badgeVariant="destructive"
              selectedTopicId={selectedTopicId}
              onSelectTopic={setSelectedTopicId}
            />
            <TopicBucketCard
              title="Developing"
              description="Topics with >=5 questions and 50%–75% accuracy."
              topics={overview.developing_topics}
              badgeVariant="warning"
              selectedTopicId={selectedTopicId}
              onSelectTopic={setSelectedTopicId}
            />
            <TopicBucketCard
              title="Strong Topics"
              description="Topics with >=5 questions and accuracy above 75%."
              topics={overview.strong_topics}
              badgeVariant="success"
              selectedTopicId={selectedTopicId}
              onSelectTopic={setSelectedTopicId}
            />
            <TopicBucketCard
              title="Insufficient Data"
              description="Fewer than 5 questions attempted — needs more samples before classifying."
              topics={overview.insufficient_data_topics}
              badgeVariant="secondary"
              selectedTopicId={selectedTopicId}
              onSelectTopic={setSelectedTopicId}
            />
          </div>

          <PerformanceTrendsChart
            trends={trends}
            isLoading={trendsLoading}
            errorMessage={trendsError}
          />

          <RevisionQueueCard
            items={overview.due_revisions}
            onUpdateStatus={handleRevisionStatus}
          />
        </>
      ) : null}
    </div>
  );
}
