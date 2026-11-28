"use client";

import Link from "next/link";
import { BookOpen, TrendingUp } from "lucide-react";

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
import { formatDurationMs } from "@/lib/api/attempts";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import type { TopicTrendsOut } from "@/lib/api/performance";
import { formatPercent, toNumber } from "@/lib/utils/number";

interface PerformanceTrendsChartProps {
  trends: TopicTrendsOut | null;
  isLoading: boolean;
  errorMessage: string | null;
}

export function PerformanceTrendsChart({
  trends,
  isLoading,
  errorMessage,
}: PerformanceTrendsChartProps) {
  if (errorMessage) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-destructive" role="alert">
          {errorMessage}
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          Loading topic trend history…
        </CardContent>
      </Card>
    );
  }

  if (!trends) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          Select a topic above to inspect accuracy and solving-speed trends
          across attempts.
        </CardContent>
      </Card>
    );
  }

  const points = trends.points;
  const maxTimeSec = Math.max(
    10,
    ...points.map((p) => Math.ceil(toNumber(p.average_time_ms, 0) / 1000)),
  );
  const width = 560;
  const height = 180;
  const padX = 36;
  const padY = 20;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;

  const accuracyPath = points
    .map((pt, idx) => {
      const x =
        points.length === 1
          ? padX + plotW / 2
          : padX + (idx / (points.length - 1)) * plotW;
      const acc = Math.max(0, Math.min(100, toNumber(pt.accuracy_percent, 0)));
      const y = padY + (1 - acc / 100) * plotH;
      return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" aria-hidden="true" />
            <CardTitle>{trends.topic_name} — Cross-Attempt Trends</CardTitle>
            <Badge variant="outline">
              {formatSubjectLabel(trends.subject_code)}
            </Badge>
            <Badge
              variant={
                trends.classification_status === "strong"
                  ? "success"
                  : trends.classification_status === "needs_practice"
                    ? "destructive"
                    : trends.classification_status === "insufficient_data"
                      ? "secondary"
                      : "warning"
              }
            >
              {trends.classification_status.replace(/_/g, " ")} (
              {trends.question_count}/{trends.min_required} min)
            </Badge>
          </div>
          <CardDescription>
            Accuracy percentage and average time per question across graded
            attempts.
          </CardDescription>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {trends.recommended_notes[0] ? (
            <Button asChild variant="outline" size="sm">
              <Link
                href={`/notes/${encodeURIComponent(trends.recommended_notes[0].id)}`}
              >
                <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Revise Notes</span>
              </Link>
            </Button>
          ) : null}
          <TargetedPracticeButton
            topicIds={[trends.topic_id]}
            label="Practise Topic"
          />
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {points.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No completed attempt snapshots recorded for this topic yet.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto rounded-md border bg-muted/20 p-3">
              <svg
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={`Accuracy trend chart for ${trends.topic_name}`}
                className="h-44 w-full min-w-[360px]"
              >
                {[0, 50, 100].map((pct) => {
                  const y = padY + (1 - pct / 100) * plotH;
                  return (
                    <g key={pct}>
                      <line
                        x1={padX}
                        y1={y}
                        x2={width - padX}
                        y2={y}
                        stroke="currentColor"
                        strokeOpacity={0.12}
                        strokeDasharray="3 3"
                      />
                      <text
                        x={padX - 6}
                        y={y + 4}
                        textAnchor="end"
                        fontSize={10}
                        fill="currentColor"
                        opacity={0.65}
                      >
                        {pct}%
                      </text>
                    </g>
                  );
                })}

                <path
                  d={accuracyPath}
                  fill="none"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2.5}
                />

                {points.map((pt, idx) => {
                  const x =
                    points.length === 1
                      ? padX + plotW / 2
                      : padX + (idx / (points.length - 1)) * plotW;
                  const acc = Math.max(
                    0,
                    Math.min(100, toNumber(pt.accuracy_percent, 0)),
                  );
                  const yAcc = padY + (1 - acc / 100) * plotH;
                  const timeRatio = Math.min(
                    1,
                    toNumber(pt.average_time_ms, 0) / 1000 / maxTimeSec,
                  );
                  const barH = timeRatio * (plotH * 0.45);
                  return (
                    <g key={pt.attempt_id}>
                      <rect
                        x={x - 6}
                        y={padY + plotH - barH}
                        width={12}
                        height={barH}
                        rx={2}
                        fill="currentColor"
                        opacity={0.15}
                      />
                      <circle
                        cx={x}
                        cy={yAcc}
                        r={4}
                        fill="hsl(var(--primary))"
                      />
                    </g>
                  );
                })}
              </svg>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Line: Accuracy (%) · Shaded bars: Avg time per question (max{" "}
                {maxTimeSec}s)
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b uppercase text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Attempt</th>
                    <th className="px-3 py-2 font-medium">Date</th>
                    <th className="px-3 py-2 font-medium">Questions</th>
                    <th className="px-3 py-2 font-medium">Accuracy</th>
                    <th className="py-2 pl-3 font-medium">Avg Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {points.map((pt) => (
                    <tr key={pt.attempt_id}>
                      <td className="py-2 pr-3 font-medium">
                        <Link
                          href={`/attempts/${encodeURIComponent(pt.attempt_id)}/results`}
                          className="text-primary hover:underline"
                        >
                          {pt.test_title}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {new Date(pt.submitted_at).toLocaleDateString()}
                      </td>
                      <td className="px-3 py-2">{pt.question_count}</td>
                      <td className="px-3 py-2 font-semibold">
                        {formatPercent(pt.accuracy_percent, 1, "0.0%")}
                      </td>
                      <td className="py-2 pl-3 text-muted-foreground">
                        {formatDurationMs(pt.average_time_ms)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
