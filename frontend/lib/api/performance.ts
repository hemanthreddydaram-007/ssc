import { apiFetch } from "@/lib/api/client";
import type { TestOut } from "@/lib/api/tests";

export type TopicClassificationStatus =
  | "strong"
  | "needs_practice"
  | "developing"
  | "insufficient_data";

export interface AnomalyQuestionOut {
  test_question_id?: string;
  question_id?: string;
  display_order?: number;
  topic_name?: string | null;
  time_spent_ms: number;
  is_correct?: boolean | null;
  status?: string;
}

export interface ErrorPatternOut {
  error_category: string;
  count: number;
  question_ids: string[];
  observation: string;
  possible_interpretation: string;
  evidence_signals: string[];
  is_tentative: boolean;
}

export interface AttemptTopicClassificationOut {
  topic_id: string | null;
  topic_name: string;
  subject_code: string | null;
  status: TopicClassificationStatus | string;
  sample_size: number;
  min_required: number;
  accuracy_percent: number;
  average_time_ms: number;
}

export interface AttemptTopicComparisonOut {
  topic_id: string;
  topic_name: string;
  current_accuracy_percent: number;
  previous_accuracy_percent: number | null;
  accuracy_delta: number | null;
  current_avg_time_ms: number;
  previous_avg_time_ms: number | null;
  time_delta_ms: number | null;
}

export interface AttemptAnalysisOut {
  attempt_id: string;
  speed_accuracy_anomalies: {
    slow_questions: AnomalyQuestionOut[];
    fast_incorrect_questions: AnomalyQuestionOut[];
  };
  error_patterns: ErrorPatternOut[];
  topic_classifications: AttemptTopicClassificationOut[];
  comparison_to_previous: AttemptTopicComparisonOut[];
}

export interface PlanRecommendationOut {
  rule_id: string;
  topic_id?: string | null;
  topic_name?: string | null;
  priority: string;
  action_type: string;
  cited_metrics: Record<string, unknown>;
  observation: string;
  possible_interpretation: string;
  recommendation: string;
  recommended_note_ids: string[];
  targeted_practice_preset?: Record<string, unknown> | null;
}

export interface AICoachingOut {
  status: string;
  summary_text: string;
  topic_explanations?: Record<string, string> | unknown[];
  model_name?: string | null;
  prompt_version?: string | null;
  grounded_only: boolean;
}

export interface ImprovementPlanOut {
  id: string;
  attempt_id: string;
  plan_version: number | string;
  rule_engine_version: string;
  recommendations: PlanRecommendationOut[];
  ai_coaching: AICoachingOut;
  created_at: string;
}

export interface TopicPerformanceOut {
  id?: string;
  topic_id: string;
  topic_name?: string;
  subject_code: string;
  attempt_count: number;
  question_count: number;
  answered_count: number;
  correct_count: number;
  timed_out_count: number;
  skipped_count: number;
  accuracy_percent: number;
  average_time_ms: number;
  classification_status: TopicClassificationStatus | string;
  latest_attempt_id?: string | null;
  previous_accuracy_percent?: number | null;
  previous_average_time_ms?: number | null;
  updated_at?: string;
}

export interface RevisionItemOut {
  id: string;
  topic_id: string;
  topic_name?: string | null;
  subject_code?: string | null;
  source_attempt_id?: string | null;
  reason_rule_id: string;
  priority: string;
  due_at: string;
  status: string;
  completed_at?: string | null;
  created_at: string;
}

export interface PerformanceOverviewOut {
  total_attempts: number;
  overall_accuracy_percent: number;
  overall_avg_time_ms: number;
  strong_topics: TopicPerformanceOut[];
  weak_topics: TopicPerformanceOut[];
  developing_topics: TopicPerformanceOut[];
  insufficient_data_topics: TopicPerformanceOut[];
  recent_improvement_deltas: AttemptTopicComparisonOut[];
  due_revisions: RevisionItemOut[];
}

export interface TopicTrendPointOut {
  attempt_id: string;
  test_title: string;
  submitted_at: string;
  question_count: number;
  accuracy_percent: number;
  average_time_ms: number;
}

export interface TopicTrendsOut {
  topic_id: string;
  topic_name: string;
  subject_code: string;
  classification_status: string;
  question_count: number;
  min_required: number;
  points: TopicTrendPointOut[];
  recommended_notes: Array<{
    id: string;
    title: string;
    note_type: string;
  }>;
}

export interface TargetedPracticeRequest {
  topic_ids: string[];
  source_attempt_id?: string;
  question_count?: number;
  difficulty_progression?: "easy_to_medium" | "mixed";
  timer_mode?: "speed_challenge" | "learning_mode";
  per_question_seconds?: number;
}

export interface TargetedPracticeResponse {
  test: TestOut;
  linked_note_ids: string[];
}

export async function getAttemptAnalysis(
  attemptId: string,
  signal?: AbortSignal,
): Promise<AttemptAnalysisOut> {
  return apiFetch<AttemptAnalysisOut>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/analysis`,
    { method: "GET", signal },
  );
}

export async function getImprovementPlan(
  attemptId: string,
  signal?: AbortSignal,
): Promise<ImprovementPlanOut> {
  return apiFetch<ImprovementPlanOut>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/improvement-plan`,
    { method: "GET", signal },
  );
}

export async function generateImprovementPlan(
  attemptId: string,
  payload: { include_ai_coaching?: boolean; force_regenerate?: boolean } = {},
): Promise<ImprovementPlanOut> {
  return apiFetch<ImprovementPlanOut>(
    `/api/v1/attempts/${encodeURIComponent(attemptId)}/improvement-plan`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function getPerformanceOverview(
  signal?: AbortSignal,
): Promise<PerformanceOverviewOut> {
  return apiFetch<PerformanceOverviewOut>("/api/v1/performance/overview", {
    method: "GET",
    signal,
  });
}

export async function listTopicPerformance(
  subjectCode?: string,
  signal?: AbortSignal,
): Promise<{ items: TopicPerformanceOut[]; total: number }> {
  const qs = subjectCode
    ? `?subject_code=${encodeURIComponent(subjectCode)}`
    : "";
  return apiFetch<{ items: TopicPerformanceOut[]; total: number }>(
    `/api/v1/performance/topics${qs}`,
    { method: "GET", signal },
  );
}

export async function getTopicTrends(
  topicId: string,
  signal?: AbortSignal,
): Promise<TopicTrendsOut> {
  return apiFetch<TopicTrendsOut>(
    `/api/v1/performance/topics/${encodeURIComponent(topicId)}/trends`,
    { method: "GET", signal },
  );
}

export async function launchTargetedPractice(
  payload: TargetedPracticeRequest,
): Promise<TargetedPracticeResponse> {
  return apiFetch<TargetedPracticeResponse>(
    "/api/v1/performance/targeted-practice",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function listRevisions(
  signal?: AbortSignal,
): Promise<{ items: RevisionItemOut[]; total: number } | RevisionItemOut[]> {
  return apiFetch<{ items: RevisionItemOut[]; total: number } | RevisionItemOut[]>(
    "/api/v1/performance/revisions",
    { method: "GET", signal },
  );
}

export async function updateRevisionStatus(
  itemId: string,
  status: "completed" | "dismissed",
): Promise<RevisionItemOut> {
  return apiFetch<RevisionItemOut>(
    `/api/v1/performance/revisions/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ status }),
    },
  );
}
