"use client";

import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Loader2,
  RefreshCw,
  SkipForward,
} from "lucide-react";

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
  formatJobStageLabel,
  formatJobTypeTitle,
  type ProcessingJobOut,
  type ProcessingStageOut,
} from "@/lib/api/jobs";
import { cn } from "@/lib/utils/cn";

interface ProcessingStagesProps {
  job: ProcessingJobOut;
  isPolling: boolean;
  pollError: string | null;
  isRetrying: boolean;
  onRetry: (jobId: string) => void;
}

function getJobStatusBadge(
  status: string,
): "success" | "warning" | "destructive" | "secondary" {
  switch (status.toLowerCase()) {
    case "completed":
    case "succeeded":
      return "success";
    case "running":
    case "processing":
    case "queued":
    case "partial_failed":
      return "warning";
    case "failed":
      return "destructive";
    default:
      return "secondary";
  }
}

function StageIcon({ status }: { status: string }) {
  switch (status.toLowerCase()) {
    case "completed":
      return (
        <CheckCircle2
          className="h-4 w-4 shrink-0 text-emerald-600"
          aria-hidden="true"
        />
      );
    case "running":
      return (
        <Loader2
          className="h-4 w-4 shrink-0 animate-spin text-primary"
          aria-hidden="true"
        />
      );
    case "failed":
      return (
        <AlertCircle
          className="h-4 w-4 shrink-0 text-destructive"
          aria-hidden="true"
        />
      );
    case "skipped":
      return (
        <SkipForward
          className="h-4 w-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
      );
    default:
      return (
        <Circle
          className="h-4 w-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
      );
  }
}

function StageCount({ stage }: { stage: ProcessingStageOut }) {
  if (
    typeof stage.processed_items === "number" &&
    typeof stage.total_items === "number" &&
    stage.total_items > 0
  ) {
    return (
      <span className="text-xs text-muted-foreground">
        {stage.processed_items} / {stage.total_items} items
      </span>
    );
  }
  return null;
}

export function ProcessingStages({
  job,
  isPolling,
  pollError,
  isRetrying,
  onRetry,
}: ProcessingStagesProps) {
  const hasRetryableFailure =
    job.status === "failed" ||
    job.status === "partial_failed" ||
    job.stages.some((s) => s.status === "failed" && s.retryable);

  const jobTitle = formatJobTypeTitle(job.job_type);
  const currentStageLabel = formatJobStageLabel(job.current_stage);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle>{jobTitle}</CardTitle>
            <Badge variant={getJobStatusBadge(job.status)} className="capitalize">
              {job.status.replace(/_/g, " ")}
            </Badge>
            {isPolling ? (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                Updating automatically…
              </span>
            ) : null}
          </div>
          <CardDescription>
            {job.document_title ? (
              <span className="font-medium text-foreground">
                {job.document_title}
                {" · "}
              </span>
            ) : null}
            Step: <strong>{currentStageLabel}</strong>
            {job.total_items > 0
              ? ` · ${job.processed_items} / ${job.total_items} items processed`
              : ""}
          </CardDescription>
        </div>

        {hasRetryableFailure ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isRetrying}
            onClick={() => onRetry(job.id)}
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", isRetrying && "animate-spin")}
              aria-hidden="true"
            />
            <span>{isRetrying ? "Retrying…" : "Retry Step"}</span>
          </Button>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-3">
        {job.error_message ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div className="min-w-0">
              <p className="font-medium">{job.error_message}</p>
              {job.error_code ? (
                <p className="mt-0.5 font-mono text-[11px] text-red-700/80">
                  Code: {job.error_code}
                </p>
              ) : null}
              {job.error_code === "AI_PROVIDER_ERROR" &&
              /429|quota/i.test(job.error_message) ? (
                <p className="mt-1.5 text-xs text-red-900">
                  Daily free-tier AI quota reached. Wait for reset or add your
                  own free AI key in{" "}
                  <Link
                    href="/settings#custom-ai-key"
                    className="font-semibold underline"
                  >
                    Settings
                  </Link>{" "}
                  and click <strong>Retry Step</strong>.
                </p>
              ) : null}
              {job.error_code === "FILE_NOT_FOUND" ? (
                <p className="mt-1.5 text-xs text-red-900">
                  Please re-upload this document once in{" "}
                  <Link href="/library" className="font-semibold underline">
                    My Library
                  </Link>{" "}
                  so it is backed by persistent database storage.
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        {pollError ? (
          <p className="text-xs text-amber-700" role="status">
            Status refresh paused: {pollError}
          </p>
        ) : null}

        {job.stages.length > 0 ? (
          <ol className="divide-y rounded-md border">
            {job.stages.map((stage) => (
              <li
                key={stage.name}
                className="flex flex-col gap-1 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex items-center gap-2.5">
                  <StageIcon status={stage.status} />
                  <div>
                    <p className="text-sm font-medium">
                      {formatJobStageLabel(stage.name)}
                    </p>
                    {stage.error_message ? (
                      <p className="text-xs text-destructive">
                        {stage.error_message}
                      </p>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center gap-3 pl-6 sm:pl-0">
                  <StageCount stage={stage} />
                  <Badge variant="outline" className="capitalize">
                    {stage.status}
                  </Badge>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">
            Starting background worker…
          </p>
        )}

        <p className="text-[11px] text-muted-foreground">
          Task reference: <span className="font-mono">{job.id}</span>
        </p>
      </CardContent>
    </Card>
  );
}
