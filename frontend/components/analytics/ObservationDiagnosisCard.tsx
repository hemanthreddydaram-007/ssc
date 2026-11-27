import { AlertTriangle, Clock, Eye } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDurationMs } from "@/lib/api/attempts";
import type { AttemptAnalysisOut } from "@/lib/api/performance";

interface ObservationDiagnosisCardProps {
  analysis: AttemptAnalysisOut;
}

export function ObservationDiagnosisCard({
  analysis,
}: ObservationDiagnosisCardProps) {
  const { slow_questions, fast_incorrect_questions } =
    analysis.speed_accuracy_anomalies;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Eye className="h-4 w-4 text-primary" aria-hidden="true" />
          <CardTitle>Timing Signals &amp; Tentative Error Patterns</CardTitle>
        </div>
        <CardDescription>
          Direct observations from response data are separated from tentative
          interpretations. Error classifications are hypotheses, not medical or
          cognitive diagnoses.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-md border bg-muted/30 p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                <Clock className="h-4 w-4 text-amber-600" aria-hidden="true" />
                Unusually Slow Questions
              </span>
              <Badge variant="outline">{slow_questions.length}</Badge>
            </div>
            {slow_questions.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No extreme slow-outlier questions detected.
              </p>
            ) : (
              <ul className="space-y-1 text-xs text-muted-foreground">
                {slow_questions.map((q, idx) => (
                  <li key={q.test_question_id ?? idx}>
                    {q.display_order ? `Q${q.display_order}` : "Question"}
                    {q.topic_name ? ` (${q.topic_name})` : ""} —{" "}
                    {formatDurationMs(q.time_spent_ms)}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-md border bg-muted/30 p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                <AlertTriangle
                  className="h-4 w-4 text-amber-600"
                  aria-hidden="true"
                />
                Fast &amp; Incorrect Attempts
              </span>
              <Badge variant="outline">{fast_incorrect_questions.length}</Badge>
            </div>
            {fast_incorrect_questions.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No rushed incorrect responses detected.
              </p>
            ) : (
              <ul className="space-y-1 text-xs text-muted-foreground">
                {fast_incorrect_questions.map((q, idx) => (
                  <li key={q.test_question_id ?? idx}>
                    {q.display_order ? `Q${q.display_order}` : "Question"}
                    {q.topic_name ? ` (${q.topic_name})` : ""} — answered in{" "}
                    {formatDurationMs(q.time_spent_ms)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {analysis.error_patterns.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No error patterns flagged in this attempt.
          </p>
        ) : (
          <div className="space-y-3">
            {analysis.error_patterns.map((pattern, idx) => (
              <div
                key={`${pattern.error_category}-${idx}`}
                className="rounded-md border p-4 space-y-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold capitalize">
                      {pattern.error_category.replace(/_/g, " ")}
                    </span>
                    <Badge variant="secondary">
                      {pattern.count}{" "}
                      {pattern.count === 1 ? "question" : "questions"}
                    </Badge>
                  </div>
                  <Badge variant="outline">Tentative classification</Badge>
                </div>

                <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
                  <div className="rounded bg-muted/40 p-2.5">
                    <p className="font-semibold text-foreground">Observation</p>
                    <p className="mt-1 text-muted-foreground">
                      {pattern.observation}
                    </p>
                  </div>
                  <div className="rounded border border-dashed bg-sky-50/40 p-2.5">
                    <p className="font-semibold text-sky-900">
                      Possible Interpretation
                    </p>
                    <p className="mt-1 text-sky-900/80">
                      {pattern.possible_interpretation}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
