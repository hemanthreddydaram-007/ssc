import { formatDurationMs, type AttemptResultsOut } from "@/lib/api/attempts";
import { formatDecimal, formatPercent } from "@/lib/utils/number";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface ResultsSummaryCardsProps {
  results: AttemptResultsOut;
}

export function ResultsSummaryCards({ results }: ResultsSummaryCardsProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Score</CardDescription>
            <CardTitle className="text-2xl">
              {formatDecimal(results.total_score)} /{" "}
              {formatDecimal(results.max_score)}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Server-graded result
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Attempted Accuracy</CardDescription>
            <CardTitle className="text-2xl">
              {formatPercent(results.accuracy_attempted_percent, 1, "0.0%")}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Overall: {formatPercent(results.accuracy_overall_percent, 1, "0.0%")}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Avg Time / Question</CardDescription>
            <CardTitle className="text-2xl">
              {formatDurationMs(results.average_time_ms)}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            Total: {formatDurationMs(results.total_time_ms)}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Outcome Breakdown</CardDescription>
            <CardTitle className="text-lg">
              {results.correct_count}C · {results.incorrect_count}W
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            {results.skipped_count} skipped · {results.timed_out_count} timed out
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
