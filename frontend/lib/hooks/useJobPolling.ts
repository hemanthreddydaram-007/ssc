"use client";

import * as React from "react";

import {
  getJob,
  isTerminalJobStatus,
  type ProcessingJobOut,
} from "@/lib/api/jobs";

interface UseJobPollingOptions {
  initialJob: ProcessingJobOut | null;
  intervalMs?: number;
  onTerminal?: (job: ProcessingJobOut) => void;
}

export function useJobPolling({
  initialJob,
  intervalMs = 2000,
  onTerminal,
}: UseJobPollingOptions) {
  const [job, setJob] = React.useState<ProcessingJobOut | null>(initialJob);
  const [pollError, setPollError] = React.useState<string | null>(null);
  const onTerminalRef = React.useRef(onTerminal);
  const notifiedJobIdRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

  React.useEffect(() => {
    if (initialJob) {
      setJob(initialJob);
      if (isTerminalJobStatus(initialJob.status)) {
        notifiedJobIdRef.current = `${initialJob.id}:${initialJob.status}`;
      }
    }
  }, [initialJob]);

  const jobId = job?.id ?? null;
  const jobStatus = job?.status ?? null;
  const shouldPoll = jobId !== null && jobStatus !== null && !isTerminalJobStatus(jobStatus);

  const pollOnce = React.useCallback(
    async (targetJobId: string, signal?: AbortSignal) => {
      try {
        const latest = await getJob(targetJobId, signal);
        setJob(latest);
        setPollError(null);
        if (isTerminalJobStatus(latest.status)) {
          const key = `${latest.id}:${latest.status}`;
          if (notifiedJobIdRef.current !== key) {
            notifiedJobIdRef.current = key;
            onTerminalRef.current?.(latest);
          }
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setPollError(
          error instanceof Error ? error.message : "Failed to poll job status.",
        );
      }
    },
    [],
  );

  React.useEffect(() => {
    if (!shouldPoll || !jobId) {
      return;
    }

    let timerId: number | null = null;
    let cancelled = false;
    const controller = new AbortController();

    const scheduleNext = () => {
      if (cancelled || document.visibilityState === "hidden") {
        return;
      }
      timerId = window.setTimeout(async () => {
        if (cancelled || document.visibilityState === "hidden") {
          return;
        }
        await pollOnce(jobId, controller.signal);
        scheduleNext();
      }, intervalMs);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        if (timerId !== null) {
          window.clearTimeout(timerId);
          timerId = null;
        }
      } else {
        void pollOnce(jobId, controller.signal).then(() => {
          if (timerId === null) {
            scheduleNext();
          }
        });
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    scheduleNext();

    return () => {
      cancelled = true;
      controller.abort();
      if (timerId !== null) {
        window.clearTimeout(timerId);
      }
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [shouldPoll, jobId, intervalMs, pollOnce]);

  const refresh = React.useCallback(async () => {
    if (!jobId) return;
    await pollOnce(jobId);
  }, [jobId, pollOnce]);

  return {
    job,
    setJob,
    isPolling: shouldPoll,
    pollError,
    refresh,
  };
}
