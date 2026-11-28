import { apiFetch } from "@/lib/api/client";
import type { TimerMode } from "@/lib/api/tests";
import {
  formatDecimal,
  formatPercent,
  toNullableNumber,
  toNumber,
} from "@/lib/utils/number";

export { formatDecimal, formatPercent, toNullableNumber, toNumber };

export interface PlayerOptionOut {
  key?: string;
  text?: string;
  option_key?: string;
  option_text?: string;
  display_order?: number;
}

export function getOptionKey(opt: PlayerOptionOut): string {
  return opt.option_key ?? opt.key ?? "";
}

export function getOptionText(opt: PlayerOptionOut): string {
  return opt.option_text ?? opt.text ?? "";
}

/**
 * Only returned in `learning_mode` with `after_question` AFTER a single response is locked.
 */
export interface LockedFeedbackOut {
  response_id?: string;
  test_question_id?: string;
  selected_option_key?: string | null;
  correct_option_key?: string | null;
  is_correct?: boolean | null;
  explanation?: string | null;
  answer_key_provenance?: string;
  source_page_number?: number | null;
  supporting_excerpt?: string | null;
}

/**
 * Active-test question payload. Strictly omits answer keys and pre-lock explanations.
 */
export interface PlayerQuestionOut {
  test_question_id: string;
  response_id?: string;
  display_order: number;
  question_text: string;
  question_type: string;
  subject_code: string;
  topic_id?: string | null;
  topic_name?: string | null;
  difficulty: string;
  passage_text?: string | null;
  diagram_asset_id?: string | null;
  document_id?: string | null;
  source_page_number?: number | null;
  options: PlayerOptionOut[];
  shown_at?: string | null;
  question_expires_at?: string | null;
  question_remaining_seconds?: number | null;
  time_limit_seconds?: number | null;
  time_spent_ms: number;
  selected_option_key?: string | null;
  status: string;
  is_marked_for_review: boolean;
  is_locked?: boolean;
  hint?: string | null;
  locked_feedback?: LockedFeedbackOut | null;
  points?: number | string;
  negative_points?: number | string;
  section_code?: string | null;
}

export interface PaletteItemOut {
  index: number;
  test_question_id: string;
  status: string;
  is_marked_for_review: boolean;
  has_answer?: boolean;
  selected_option_key?: string | null;
  is_locked?: boolean;
}

export function isPaletteItemAnswered(item: PaletteItemOut): boolean {
  return Boolean(
    item.has_answer || item.selected_option_key || item.status === "answered",
  );
}

export interface AttemptSettingsOut {
  timer_mode: TimerMode | string;
  per_question_seconds?: number | null;
  total_duration_seconds?: number | null;
  auto_advance_on_timeout?: boolean;
  show_explanation_after?: string;
  points_per_question?: string | number;
  negative_marking_enabled?: boolean;
  negative_points?: string | number;
  hints_enabled?: boolean;
}

export interface AttemptCurrentOut {
  attempt_id: string;
  test_id: string;
  test_title?: string | null;
  status: string;
  timer_mode: TimerMode | string;
  server_now: string;
  started_at: string;
  attempt_expires_at: string | null;
  attempt_remaining_seconds?: number | null;
  current_question_index: number;
  total_questions: number;
  current_question: PlayerQuestionOut | null;
  palette: PaletteItemOut[];
  settings: AttemptSettingsOut;
  locked_feedback?: LockedFeedbackOut | null;
}

export interface AttemptSummaryOut {
  attempt_id: string;
  id?: string;
  test_id: string;
  test_title?: string | null;
  timer_mode: string;
  status: string;
  started_at: string;
  submitted_at: string | null;
  total_score: number | string | null;
  max_score: number | string;
  total_time_ms: number;
  total_questions?: number;
  correct_count: number;
  incorrect_count: number;
  skipped_count: number;
  timed_out_count: number;
}

export function getAttemptId(attempt: AttemptSummaryOut): string {
  return attempt.attempt_id ?? attempt.id ?? "";
}

export interface AttemptListResponse {
  items: AttemptSummaryOut[];
  total: number;
}

export type ResponseAction =
  | "answer"
  | "skip"
  | "mark_review"
  | "unmark_review";

export interface ResponseSaveRequest {
  test_question_id: string;
  selected_option_key?: string | null;
  action?: ResponseAction;
  is_marked_for_review?: boolean;
  advance?: boolean;
}

export interface ResponseSaveOut {
  attempt_id: string;
  response_id: string;
  test_question_id?: string;
  status: string;
  selected_option_key?: string | null;
  is_marked_for_review: boolean;
  is_locked?: boolean;
  time_spent_ms?: number;
  current_question_index?: number;
  server_now?: string;
  locked_feedback?: LockedFeedbackOut | null;
  next_state?: AttemptCurrentOut | null;
}

export interface SelfReportRequest {
  confidence_self_report?: string | null;
  mistake_reason_self_report?: string | null;
}

export interface TopicBreakdownItem {
  topic_id: string | null;
  topic_name: string;
  subject_code?: string | null;
  total_questions: number;
  attempted_count: number;
  correct_count: number;
  incorrect_count: number;
  skipped_count: number;
  timed_out_count: number;
  accuracy_percent: number | string;
  average_time_ms: number;
}

export interface DifficultyBreakdownItem {
  difficulty: string;
  total_questions: number;
  attempted_count?: number;
  correct_count: number;
  incorrect_count: number;
  skipped_count?: number;
  timed_out_count?: number;
  accuracy_percent: number | string;
  average_time_ms?: number;
}

export interface QuestionReviewOut {
  response_id: string;
  test_question_id: string;
  question_id?: string | null;
  display_order: number;
  subject_code: string;
  topic_id?: string | null;
  topic_name?: string | null;
  difficulty: string;
  origin?: string;
  question_text: string;
  passage_text?: string | null;
  document_id?: string | null;
  source_document_id?: string | null;
  source_page_number?: number | null;
  supporting_excerpt?: string | null;
  diagram_asset_id?: string | null;
  options: PlayerOptionOut[];
  selected_option_key: string | null;
  correct_option_key: string | null;
  is_correct: boolean | null;
  status: string;
  graded_points: number | string | null;
  time_spent_ms: number;
  is_marked_for_review?: boolean;
  explanation: string;
  answer_key_provenance?: string | null;
  confidence_self_report?: string | null;
  mistake_reason_self_report?: string | null;
}

export interface AttemptResultsOut {
  attempt_id: string;
  test_id: string;
  test_title?: string | null;
  timer_mode: string;
  status: string;
  started_at: string;
  submitted_at: string | null;
  total_score: number | string;
  max_score: number | string;
  total_time_ms: number;
  total_questions?: number;
  correct_count: number;
  incorrect_count: number;
  skipped_count: number;
  timed_out_count: number;
  accuracy_attempted_percent: number | string;
  accuracy_overall_percent: number | string;
  average_time_ms: number;
  topic_breakdown: TopicBreakdownItem[];
  difficulty_breakdown: DifficultyBreakdownItem[];
  questions: QuestionReviewOut[];
}

export async function startTestAttempt(
  testId: string,
): Promise<AttemptCurrentOut> {
  return apiFetch<AttemptCurrentOut>(
    `/api/v1/tests/${encodeURIComponent(testId)}/start`,
    {
      method: "POST",
    },
  );
}

export async function listAttempts(
  query: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<AttemptListResponse> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();

  return apiFetch<AttemptListResponse>(
    `/api/v1/attempts${qs ? `?${qs}` : ""}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function getAttemptCurrent(
  attemptId: string,
  signal?: AbortSignal,
): Promise<AttemptCurrentOut> {
  return apiFetch<AttemptCurrentOut>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/current`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function navigateAttempt(
  attemptId: string,
  targetIndex: number,
): Promise<AttemptCurrentOut> {
  return apiFetch<AttemptCurrentOut>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/navigate`,
    {
      method: "POST",
      body: JSON.stringify({ target_index: targetIndex }),
    },
  );
}

export async function saveAttemptResponse(
  attemptId: string,
  payload: ResponseSaveRequest,
): Promise<ResponseSaveOut> {
  return apiFetch<ResponseSaveOut>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/responses`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function saveSelfReport(
  attemptId: string,
  responseId: string,
  payload: SelfReportRequest,
): Promise<void> {
  await apiFetch<unknown>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/responses/${encodeURIComponent(responseId)}/self-report`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function submitAttempt(
  attemptId: string,
): Promise<AttemptSummaryOut> {
  return apiFetch<AttemptSummaryOut>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/submit`,
    {
      method: "POST",
    },
  );
}

export async function getAttemptResults(
  attemptId: string,
  signal?: AbortSignal,
): Promise<AttemptResultsOut> {
  return apiFetch<AttemptResultsOut>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/results`,
    {
      method: "GET",
      signal,
    },
  );
}

export function formatDurationMs(
  ms: number | string | null | undefined,
): string {
  const safeMs = toNumber(ms, 0);
  const totalSeconds = Math.max(0, Math.round(safeMs / 1000));
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  if (mins === 0) {
    return `${secs}s`;
  }
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}
