import { apiFetch } from "@/lib/api/client";

export interface QuestionOptionOut {
  id?: string;
  option_key: string;
  option_text: string;
  display_order?: number;
}

export interface QuestionOut {
  id: string;
  document_id: string | null;
  topic_id: string | null;
  topic_name?: string | null;
  concept_id?: string | null;
  exam_config_id?: string | null;
  subject_code: string;
  question_text: string;
  question_type: string;
  difficulty: string;
  origin: string;
  source_page_number: number | null;
  supporting_excerpt?: string | null;
  diagram_asset_id?: string | null;
  passage_group_id?: string | null;
  passage_text?: string | null;
  pyq_metadata_json?: Record<string, unknown> | null;
  answer_key_provenance: string;
  validation_status: string;
  options: QuestionOptionOut[];
  created_at: string;
}

export interface QuestionDetailOut extends QuestionOut {
  correct_answer_data: {
    correct_option_key?: string | null;
    [key: string]: unknown;
  };
  explanation: string;
  validation_warnings?: string[];
  model_name?: string | null;
  prompt_version?: string | null;
  updated_at?: string;
}

export interface QuestionListResponse {
  items: QuestionOut[];
  total: number;
}

export interface QuestionListQuery {
  document_id?: string;
  subject_code?: string;
  topic_id?: string;
  difficulty?: string;
  origin?: string;
  validation_status?: string;
  pyq_year?: number;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface GenerateQuestionsRequest {
  document_id?: string | null;
  topic_id?: string | null;
  concept_id?: string | null;
  subject_code?: string | null;
  difficulty?: "easy" | "medium" | "hard" | "mixed";
  count?: number;
}

export interface GenerateQuestionsResponse {
  created: QuestionDetailOut[];
  verified_count: number;
  needs_review_count: number;
  duplicates_skipped: number;
}

export interface ImportQuestionItem {
  question_text: string;
  options: Array<{ key: string; text: string }>;
  correct_option_key?: string | null;
  explanation?: string;
  subject_code?: string;
  topic_name?: string;
  difficulty?: string;
  source_page_number?: number;
  pyq_metadata?: Record<string, unknown>;
  passage_text?: string;
}

export interface ImportQuestionsRequest {
  document_id?: string | null;
  exam_config_id?: string | null;
  default_subject_code?: string | null;
  answer_key_provenance?: "source_answer_key" | "user_supplied";
  items: ImportQuestionItem[];
}

export interface ImportQuestionsResponse {
  imported_count: number;
  verified_count: number;
  needs_review_count: number;
  duplicates_skipped: number;
  items: QuestionDetailOut[];
}

export interface UpdateQuestionRequest {
  question_text?: string;
  options?: Array<{ key: string; text: string }>;
  correct_option_key?: string;
  explanation?: string;
  difficulty?: string;
  topic_id?: string | null;
  validation_status?: string;
}

function buildQueryString(query: QuestionListQuery): string {
  const params = new URLSearchParams();
  if (query.document_id) params.set("document_id", query.document_id);
  if (query.subject_code) params.set("subject_code", query.subject_code);
  if (query.topic_id) params.set("topic_id", query.topic_id);
  if (query.difficulty) params.set("difficulty", query.difficulty);
  if (query.origin) params.set("origin", query.origin);
  if (query.validation_status) {
    params.set("validation_status", query.validation_status);
  }
  if (query.pyq_year !== undefined) {
    params.set("pyq_year", String(query.pyq_year));
  }
  if (query.q && query.q.trim().length > 0) params.set("q", query.q.trim());
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  return params.toString();
}

export async function listQuestions(
  query: QuestionListQuery = {},
  signal?: AbortSignal,
): Promise<QuestionListResponse> {
  const qs = buildQueryString(query);
  return apiFetch<QuestionListResponse>(
    `/api/v1/questions${qs ? `?${qs}` : ""}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function listDocumentQuestions(
  documentId: string,
  query: Omit<QuestionListQuery, "document_id"> = {},
  signal?: AbortSignal,
): Promise<QuestionListResponse> {
  const qs = buildQueryString(query);
  return apiFetch<QuestionListResponse>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/questions${qs ? `?${qs}` : ""}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function getQuestionDetail(
  questionId: string,
  signal?: AbortSignal,
): Promise<QuestionDetailOut> {
  return apiFetch<QuestionDetailOut>(
    `/api/v1/questions/${encodeURIComponent(questionId)}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function generateQuestions(
  payload: GenerateQuestionsRequest,
): Promise<GenerateQuestionsResponse> {
  return apiFetch<GenerateQuestionsResponse>("/api/v1/questions/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function importQuestions(
  payload: ImportQuestionsRequest,
): Promise<ImportQuestionsResponse> {
  return apiFetch<ImportQuestionsResponse>("/api/v1/questions/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateQuestion(
  questionId: string,
  payload: UpdateQuestionRequest,
): Promise<QuestionDetailOut> {
  return apiFetch<QuestionDetailOut>(
    `/api/v1/questions/${encodeURIComponent(questionId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteQuestion(
  questionId: string,
): Promise<{ deleted_id: string }> {
  return apiFetch<{ deleted_id: string }>(
    `/api/v1/questions/${encodeURIComponent(questionId)}`,
    {
      method: "DELETE",
    },
  );
}
