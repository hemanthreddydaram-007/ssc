import { apiFetch } from "@/lib/api/client";
import type { AttemptSummaryOut } from "@/lib/api/attempts";
import type { DocumentItem } from "@/lib/api/documents";
import type { ProcessingJobOut } from "@/lib/api/jobs";
import type {
  RevisionItemOut,
  TopicPerformanceOut,
} from "@/lib/api/performance";

export interface DashboardTotalsOut {
  documents_count: number;
  notes_count: number;
  questions_count: number;
  completed_attempts_count: number;
}

export interface DashboardSummaryOut {
  continue_attempt: AttemptSummaryOut | null;
  recent_documents: DocumentItem[];
  active_jobs: ProcessingJobOut[];
  recent_attempts: AttemptSummaryOut[];
  weak_topics: TopicPerformanceOut[];
  due_revisions: RevisionItemOut[];
  totals: DashboardTotalsOut;
}

export async function getDashboardSummary(
  signal?: AbortSignal,
): Promise<DashboardSummaryOut> {
  return apiFetch<DashboardSummaryOut>("/api/v1/dashboard", {
    method: "GET",
    signal,
  });
}
