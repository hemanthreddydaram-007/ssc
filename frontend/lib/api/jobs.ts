import { apiFetch } from "@/lib/api/client";

export type StageStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | string;

export interface ProcessingStageOut {
  name: string;
  status: StageStatus;
  processed_items?: number | null;
  total_items?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  retryable: boolean;
}

export interface ProcessingJobOut {
  id: string;
  document_id: string;
  job_type: string;
  status: string;
  current_stage: string;
  stages: ProcessingStageOut[];
  processed_items: number;
  total_items: number;
  progress_percent: number | null;
  error_code: string | null;
  error_message: string | null;
  retry_count: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export type ProcessMode = "extract_only" | "full" | "ocr_retry";

export interface ProcessDocumentRequest {
  mode?: ProcessMode;
  page_numbers?: number[];
  force_reextract?: boolean;
}

type JobListResponse = ProcessingJobOut[] | { items: ProcessingJobOut[] };

const TERMINAL_JOB_STATUSES = new Set([
  "completed",
  "failed",
  "partial_failed",
  "cancelled",
  "succeeded",
]);

export function isTerminalJobStatus(status: string): boolean {
  return TERMINAL_JOB_STATUSES.has(status.toLowerCase());
}

export async function processDocument(
  documentId: string,
  payload: ProcessDocumentRequest = { mode: "extract_only" },
): Promise<ProcessingJobOut> {
  return apiFetch<ProcessingJobOut>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/process`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function listJobs(
  query: { document_id?: string; status?: string } = {},
  signal?: AbortSignal,
): Promise<ProcessingJobOut[]> {
  const params = new URLSearchParams();
  if (query.document_id) params.set("document_id", query.document_id);
  if (query.status) params.set("status", query.status);
  const qs = params.toString();

  const data = await apiFetch<JobListResponse>(
    `/api/v1/jobs${qs ? `?${qs}` : ""}`,
    {
      method: "GET",
      signal,
    },
  );
  return Array.isArray(data) ? data : data.items;
}

export async function getJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<ProcessingJobOut> {
  return apiFetch<ProcessingJobOut>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function retryJob(jobId: string): Promise<ProcessingJobOut> {
  return apiFetch<ProcessingJobOut>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/retry`,
    {
      method: "POST",
    },
  );
}
