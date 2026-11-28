import { apiFetch } from "@/lib/api/client";

export type StageStatus =
  | "pending"
  | "queued"
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
  document_title?: string | null;
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

const JOB_TYPE_TITLES: Record<string, string> = {
  extract_only: "Extracting Document Pages",
  full: "Full Document Processing",
  ocr_retry: "Retrying OCR Text Extraction",
  extract_knowledge: "AI Knowledge & Question Extraction",
  generate_notes: "Generating Smart Notes",
};

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued for processing",
  page_extraction: "Reading pages & tables",
  extracting_pages: "Reading pages & tables",
  scan_detection: "Checking scanned / image pages",
  ocr: "Running OCR text recognition",
  chunking: "Splitting into study sections",
  coverage_audit: "Summarizing extracted coverage",
  classification: "Detecting subject & topics",
  classifying: "Detecting subject & topics",
  knowledge_extraction: "Extracting concepts, facts & questions",
  extracting_knowledge: "Extracting concepts, facts & questions",
  question_ingestion: "Saving extracted questions",
  note_generation: "Writing smart notes & formulas",
  generating_notes: "Writing smart notes & formulas",
  finalizing: "Saving results",
};

export function formatJobTypeTitle(jobType: string): string {
  const key = jobType.trim().toLowerCase();
  if (JOB_TYPE_TITLES[key]) {
    return JOB_TYPE_TITLES[key];
  }
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatJobStageLabel(stageName: string): string {
  const key = stageName.trim().toLowerCase();
  if (STAGE_LABELS[key]) {
    return STAGE_LABELS[key];
  }
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
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
