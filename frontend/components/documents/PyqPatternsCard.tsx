"use client";

import { BarChart2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import type { PyqPatternsOut } from "@/lib/api/notes";
import { formatPercent } from "@/lib/utils/number";

interface PyqPatternsCardProps {
  patterns: PyqPatternsOut | null;
  isLoading: boolean;
  errorMessage: string | null;
}

export function PyqPatternsCard({
  patterns,
  isLoading,
  errorMessage,
}: PyqPatternsCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <BarChart2 className="h-4 w-4 text-primary" aria-hidden="true" />
          <CardTitle>PYQ Pattern Analysis</CardTitle>
        </div>
        <CardDescription>
          Sample-scoped frequency counts across extracted questions in this
          document. Every percentage is paired with the exact sample
          denominator.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {errorMessage ? (
          <p className="text-sm text-destructive" role="alert">
            {errorMessage}
          </p>
        ) : isLoading ? (
          <p className="text-sm text-muted-foreground">
            Loading PYQ pattern stats…
          </p>
        ) : !patterns || patterns.total_questions_analyzed === 0 ? (
          <p className="text-sm text-muted-foreground">
            No extracted questions analyzed in this document yet.
          </p>
        ) : (
          <>
            <div className="rounded-md border bg-muted/40 p-3 text-xs text-muted-foreground">
              <strong className="text-foreground">Sample scope:</strong>{" "}
              {patterns.total_questions_analyzed} questions analyzed.{" "}
              {patterns.sample_note}
            </div>

            {patterns.topics.length > 0 ? (
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Topic Frequency (n = {patterns.total_questions_analyzed})
                </h4>
                <div className="flex flex-wrap gap-2">
                  {patterns.topics.map((t) => (
                    <Badge key={t.topic_name} variant="secondary">
                      {t.topic_name}: {t.count}/{patterns.total_questions_analyzed}{" "}
                      ({formatPercent(t.percentage, 1, "0.0%")})
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {patterns.subjects.length > 0 ? (
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Subject Distribution
                </h4>
                <div className="flex flex-wrap gap-2">
                  {patterns.subjects.map((s) => (
                    <Badge key={s.subject_code} variant="outline">
                      {formatSubjectLabel(s.subject_code)}: {s.count}/
                      {patterns.total_questions_analyzed} (
                      {formatPercent(s.percentage, 1, "0.0%")})
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
