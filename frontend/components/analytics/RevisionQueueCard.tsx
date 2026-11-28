"use client";

import * as React from "react";
import Link from "next/link";
import { BookOpen, CalendarClock, Check, X } from "lucide-react";

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
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import type { RevisionItemOut } from "@/lib/api/performance";
import { normalizePriority } from "@/lib/utils/number";

interface RevisionQueueCardProps {
  items: readonly RevisionItemOut[];
  onUpdateStatus: (
    itemId: string,
    status: "completed" | "dismissed",
  ) => Promise<void>;
}

export function RevisionQueueCard({
  items,
  onUpdateStatus,
}: RevisionQueueCardProps) {
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const handleAction = async (
    id: string,
    status: "completed" | "dismissed",
  ) => {
    setBusyId(id);
    try {
      await onUpdateStatus(id, status);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-primary" aria-hidden="true" />
          <CardTitle>Due Revision Queue ({items.length})</CardTitle>
        </div>
        <CardDescription>
          Topics queued for review based on recent test accuracy and speed
          rules.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No pending revision items right now.
          </p>
        ) : (
          <div className="space-y-3">
            {items.map((item) => {
              const priorityTier = normalizePriority(item.priority);
              return (
                <div
                  key={item.id}
                  className="flex flex-col gap-3 rounded-md border p-3.5 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">
                        {item.topic_name ?? "Topic Revision"}
                      </span>
                      {item.subject_code ? (
                        <Badge variant="outline">
                          {formatSubjectLabel(item.subject_code)}
                        </Badge>
                      ) : null}
                      <Badge
                        variant={
                          priorityTier === "high"
                            ? "destructive"
                            : priorityTier === "medium"
                              ? "warning"
                              : "secondary"
                        }
                        className="capitalize"
                      >
                        {priorityTier} priority
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Due {new Date(item.due_at).toLocaleDateString()} · Trigger:{" "}
                      {item.reason_rule_id}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button asChild variant="outline" size="sm">
                      <Link
                        href={`/notes?topic_id=${encodeURIComponent(item.topic_id)}`}
                      >
                        <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>Notes</span>
                      </Link>
                    </Button>
                    <TargetedPracticeButton
                      topicIds={[item.topic_id]}
                      label="Practise"
                      variant="outline"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busyId === item.id}
                      onClick={() => void handleAction(item.id, "completed")}
                    >
                      <Check
                        className="h-3.5 w-3.5 text-emerald-600"
                        aria-hidden="true"
                      />
                      <span>Done</span>
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label="Dismiss revision item"
                      disabled={busyId === item.id}
                      onClick={() => void handleAction(item.id, "dismissed")}
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
