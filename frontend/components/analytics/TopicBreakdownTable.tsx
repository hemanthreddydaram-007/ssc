import {
  formatDurationMs,
  type DifficultyBreakdownItem,
  type TopicBreakdownItem,
} from "@/lib/api/attempts";
import { formatPercent } from "@/lib/utils/number";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface TopicBreakdownTableProps {
  topics: readonly TopicBreakdownItem[];
  difficulties: readonly DifficultyBreakdownItem[];
}

export function TopicBreakdownTable({
  topics,
  difficulties,
}: TopicBreakdownTableProps) {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Topic Breakdown</CardTitle>
          <CardDescription>
            Accuracy and average solving time per topic in this attempt.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {topics.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No topic breakdown available.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Topic</th>
                    <th className="px-3 py-2 font-medium">Correct</th>
                    <th className="px-3 py-2 font-medium">Wrong</th>
                    <th className="px-3 py-2 font-medium">Skip / T.O.</th>
                    <th className="px-3 py-2 font-medium">Accuracy</th>
                    <th className="py-2 pl-3 font-medium">Avg Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {topics.map((t, idx) => (
                    <tr key={`${t.topic_id ?? "none"}-${idx}`}>
                      <td className="py-2.5 pr-3 font-medium">
                        {t.topic_name}
                      </td>
                      <td className="px-3 py-2.5 text-emerald-700">
                        {t.correct_count}
                      </td>
                      <td className="px-3 py-2.5 text-red-700">
                        {t.incorrect_count}
                      </td>
                      <td className="px-3 py-2.5 text-muted-foreground">
                        {t.skipped_count} / {t.timed_out_count}
                      </td>
                      <td className="px-3 py-2.5 font-medium">
                        {formatPercent(t.accuracy_percent, 1, "0.0%")}
                      </td>
                      <td className="py-2.5 pl-3 text-muted-foreground">
                        {formatDurationMs(t.average_time_ms)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Difficulty Breakdown</CardTitle>
          <CardDescription>Accuracy across difficulty tiers.</CardDescription>
        </CardHeader>
        <CardContent>
          {difficulties.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No difficulty metrics available.
            </p>
          ) : (
            <div className="space-y-3">
              {difficulties.map((d) => (
                <div
                  key={d.difficulty}
                  className="flex items-center justify-between rounded-md border bg-muted/30 p-3 text-sm"
                >
                  <div>
                    <p className="font-medium capitalize">{d.difficulty}</p>
                    <p className="text-xs text-muted-foreground">
                      {d.correct_count}/{d.total_questions} correct
                    </p>
                  </div>
                  <span className="font-semibold">
                    {formatPercent(d.accuracy_percent, 1, "0.0%")}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
