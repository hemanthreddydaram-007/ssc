import { apiFetch } from "@/lib/api/client";

export type TimerMode = "speed_challenge" | "exam_simulation" | "learning_mode";
export type OriginMode = "extracted" | "generated" | "mixed";
export type ShowExplanationAfter = "after_question" | "after_submission";

export interface DifficultyMix {
  easy?: number;
  medium?: number;
  hard?: number;
}

export interface TestPreviewRequest {
  document_ids?: string[];
  subject_codes?: string[];
  topic_ids?: string[];
  question_ids?: string[];
  origin_mode?: OriginMode;
  difficulty_mix?: DifficultyMix;
  question_count?: number;
  include_needs_review?: boolean;
}

export interface TestPreviewResponse {
  available_count: number;
  by_difficulty: {
    easy?: number;
    medium?: number;
    hard?: number;
    [key: string]: number | undefined;
  };
  by_subject: Record<string, number>;
  can_satisfy: boolean;
  shortfall_reason?: string | null;
}

export interface CreateTestRequest {
  title: string;
  exam_config_id?: string | null;
  document_ids?: string[];
  subject_codes?: string[];
  topic_ids?: string[];
  question_ids?: string[];
  question_count: number;
  origin_mode: OriginMode;
  difficulty_mix?: DifficultyMix;
  timer_mode: TimerMode;
  per_question_seconds: number;
  total_duration_seconds?: number | null;
  auto_advance_on_timeout: boolean;
  points_per_question: number;
  negative_marking_enabled: boolean;
  negative_points: number;
  shuffle_questions: boolean;
  shuffle_options: boolean;
  show_explanation_after: ShowExplanationAfter;
  include_needs_review: boolean;
}

export interface TestOut {
  id: string;
  user_id: string;
  title: string;
  exam_config_id: string | null;
  subject_code: string | null;
  source_document_ids_json: string[];
  settings_json: Record<string, unknown>;
  total_questions: number;
  max_score: number | string;
  status: string;
  created_at: string;
}

export interface TestListResponse {
  items: TestOut[];
  total: number;
}

export async function previewTest(
  payload: TestPreviewRequest,
  signal?: AbortSignal,
): Promise<TestPreviewResponse> {
  return apiFetch<TestPreviewResponse>("/api/v1/tests/preview", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export async function createTest(payload: CreateTestRequest): Promise<TestOut> {
  return apiFetch<TestOut>("/api/v1/tests", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listTests(
  query: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<TestListResponse> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();

  return apiFetch<TestListResponse>(`/api/v1/tests${qs ? `?${qs}` : ""}`, {
    method: "GET",
    signal,
  });
}

export async function getTest(
  testId: string,
  signal?: AbortSignal,
): Promise<TestOut> {
  return apiFetch<TestOut>(`/api/v1/tests/${encodeURIComponent(testId)}`, {
    method: "GET",
    signal,
  });
}

export function formatTimerModeLabel(mode: string): string {
  switch (mode) {
    case "speed_challenge":
      return "Speed Challenge";
    case "exam_simulation":
      return "Exam Simulation";
    case "learning_mode":
      return "Learning Mode";
    default:
      return mode.replace(/_/g, " ");
  }
}
