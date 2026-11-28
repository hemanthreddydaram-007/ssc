import { apiFetch } from "@/lib/api/client";
import type { ProcessingJobOut } from "@/lib/api/jobs";

export type NoteType =
  | "detailed"
  | "quick_revision"
  | "formula_sheet"
  | "strategy_sheet";

export type NoteBlockType =
  | "concept"
  | "definition"
  | "step"
  | "worked_example"
  | "formula"
  | "rule"
  | "misconception"
  | "comparison"
  | "mnemonic"
  | "recap"
  | "strategy"
  | "warning";

export type ProvenanceType =
  | "extracted"
  | "paraphrased"
  | "ai_explanation"
  | "externally_verified"
  | "unverified";

export type ReviewStatusType = "verified" | "needs_review" | "conflict";

export interface NoteSourceRef {
  document_id?: string | null;
  page_number: number | null;
  supporting_excerpt?: string | null;
}

export interface NoteBlockOut {
  block_type: NoteBlockType | string;
  title?: string | null;
  body: string;
  formula_latex?: string | null;
  metadata?: Record<string, unknown> | null;
  provenance: ProvenanceType | string;
  source_refs: NoteSourceRef[];
  review_status: ReviewStatusType | string;
}

export interface NoteSectionOut {
  key: string;
  title: string;
  blocks: NoteBlockOut[];
}

export interface NoteContentJson {
  summary: string;
  sections: NoteSectionOut[];
  one_minute_recap?: string | null;
  insufficient_evidence_message?: string | null;
}

export interface NoteSummaryOut {
  id: string;
  document_id: string;
  topic_id: string | null;
  topic_name?: string | null;
  subject_code: string | null;
  note_type: NoteType | string;
  title: string;
  generation_version: number;
  status: string;
  understood_at: string | null;
  created_at: string;
}

export interface NoteDetailOut extends NoteSummaryOut {
  content_json: NoteContentJson;
  source_concept_ids: string[];
  source_fact_ids: string[];
  model_name: string | null;
  prompt_name: string | null;
  prompt_version: string | null;
  error_message: string | null;
}

export interface NoteListResponse {
  items: NoteSummaryOut[];
  total: number;
}

export interface GenerateNotesRequest {
  note_types?: NoteType[];
  topic_ids?: string[];
  force_regenerate?: boolean;
}

export interface RegenerateNoteRequest {
  section_keys?: string[];
  custom_instruction?: string;
}

export interface NotesListQuery {
  document_id?: string;
  note_type?: string;
  topic_id?: string;
  subject_code?: string;
  status?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface PyqSubjectStat {
  subject_code: string;
  count: number;
  percentage: number | string;
}

export interface PyqTopicStat {
  topic_id?: string | null;
  topic_name: string;
  count: number;
  percentage: number | string;
}

export interface PyqPatternsOut {
  document_id: string;
  total_questions_analyzed: number;
  sample_note: string;
  subjects: PyqSubjectStat[];
  topics: PyqTopicStat[];
  difficulty_distribution: Record<string, number>;
  years_shifts: unknown[];
  repeated_templates: unknown[];
}

export const NOTE_TYPE_LABELS: Record<string, string> = {
  detailed: "Detailed Notes",
  quick_revision: "Quick Revision",
  formula_sheet: "Formula Sheet",
  strategy_sheet: "Solving Strategies",
};

export function formatNoteType(noteType: string): string {
  return (
    NOTE_TYPE_LABELS[noteType] ??
    noteType
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ")
  );
}

export async function generateDocumentNotes(
  documentId: string,
  payload: GenerateNotesRequest = {},
): Promise<ProcessingJobOut> {
  return apiFetch<ProcessingJobOut>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/generate-notes`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function listDocumentNotes(
  documentId: string,
  query: Omit<NotesListQuery, "document_id"> = {},
  signal?: AbortSignal,
): Promise<NoteListResponse> {
  const params = new URLSearchParams();
  if (query.note_type) params.set("note_type", query.note_type);
  if (query.topic_id) params.set("topic_id", query.topic_id);
  if (query.subject_code) params.set("subject_code", query.subject_code);
  if (query.status) params.set("status", query.status);
  if (query.q && query.q.trim().length > 0) params.set("q", query.q.trim());
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();

  return apiFetch<NoteListResponse>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/notes${qs ? `?${qs}` : ""}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function listNotes(
  query: NotesListQuery = {},
  signal?: AbortSignal,
): Promise<NoteListResponse> {
  const params = new URLSearchParams();
  if (query.document_id) params.set("document_id", query.document_id);
  if (query.note_type) params.set("note_type", query.note_type);
  if (query.topic_id) params.set("topic_id", query.topic_id);
  if (query.subject_code) params.set("subject_code", query.subject_code);
  if (query.status) params.set("status", query.status);
  if (query.q && query.q.trim().length > 0) params.set("q", query.q.trim());
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();

  return apiFetch<NoteListResponse>(`/api/v1/notes${qs ? `?${qs}` : ""}`, {
    method: "GET",
    signal,
  });
}

export async function getNote(
  noteId: string,
  signal?: AbortSignal,
): Promise<NoteDetailOut> {
  return apiFetch<NoteDetailOut>(
    `/api/v1/notes/${encodeURIComponent(noteId)}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function regenerateNote(
  noteId: string,
  payload: RegenerateNoteRequest = {},
): Promise<NoteDetailOut> {
  return apiFetch<NoteDetailOut>(
    `/api/v1/notes/${encodeURIComponent(noteId)}/regenerate`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function updateNote(
  noteId: string,
  payload: { understood?: boolean; status?: string },
): Promise<NoteDetailOut> {
  return apiFetch<NoteDetailOut>(
    `/api/v1/notes/${encodeURIComponent(noteId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function getDocumentPyqPatterns(
  documentId: string,
  signal?: AbortSignal,
): Promise<PyqPatternsOut> {
  return apiFetch<PyqPatternsOut>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/pyq-patterns`,
    {
      method: "GET",
      signal,
    },
  );
}
