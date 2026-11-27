import { apiFetch } from "@/lib/api/client";
import type { DocumentItem } from "@/lib/api/documents";
import type { ProcessingJobOut } from "@/lib/api/jobs";

export interface SourceRefOut {
  document_id?: string | null;
  page_number?: number | null;
  section_title?: string | null;
  supporting_excerpt?: string | null;
  provenance?: string | null;
}

export interface TopicSummaryOut {
  id: string;
  subject_code: string;
  name: string;
  slug: string;
  description?: string | null;
  is_canonical?: boolean;
  fact_count?: number;
  concept_count?: number;
}

export interface ConceptOut {
  id: string;
  document_id: string;
  topic_id: string | null;
  title: string;
  explanation: string;
  difficulty: string | null;
  provenance: string;
  confidence: number;
  review_status: string;
  source_refs_json?: SourceRefOut[];
  prerequisites_json?: string[];
  model_name?: string | null;
  prompt_version?: string | null;
  created_at: string;
}

export interface FactOut {
  id: string;
  document_id: string;
  topic_id: string | null;
  fact_type: string;
  content: string;
  provenance: string;
  confidence: number;
  source_page_number: number | null;
  supporting_excerpt: string | null;
  source_refs_json?: SourceRefOut[];
  conflict_group_id?: string | null;
  is_time_sensitive?: boolean;
  source_date_label?: string | null;
  review_status: string;
  model_name?: string | null;
  prompt_version?: string | null;
  created_at: string;
}

export interface DocumentKnowledgeOut {
  document_id: string;
  subject_code: string | null;
  detected_subject_code: string | null;
  classification_confidence: number | null;
  topics: TopicSummaryOut[];
  concepts: ConceptOut[];
  facts: FactOut[];
  rejected_or_uncertain_count: number;
}

export interface SubjectOut {
  subject_code: string;
  display_name: string;
  supported_strategies: string[];
}

export interface ClassificationOverrideRequest {
  subject_code?: string | null;
  material_type?: string;
  language?: string;
}

export interface FactUpdateRequest {
  content?: string;
  fact_type?: string;
  review_status?: string;
}

export async function extractKnowledge(
  documentId: string,
  forceReprocess = false,
): Promise<ProcessingJobOut> {
  return apiFetch<ProcessingJobOut>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/extract-knowledge`,
    {
      method: "POST",
      body: JSON.stringify({ force_reprocess: forceReprocess }),
    },
  );
}

export async function overrideDocumentClassification(
  documentId: string,
  payload: ClassificationOverrideRequest,
): Promise<DocumentItem> {
  return apiFetch<DocumentItem>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/classification`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function getDocumentKnowledge(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentKnowledgeOut> {
  return apiFetch<DocumentKnowledgeOut>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/knowledge`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function getDocumentTopics(
  documentId: string,
  signal?: AbortSignal,
): Promise<{ items: TopicSummaryOut[]; total: number }> {
  return apiFetch<{ items: TopicSummaryOut[]; total: number }>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/topics`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function listAllTopics(
  subjectCode?: string,
  signal?: AbortSignal,
): Promise<{ items: TopicSummaryOut[]; total: number }> {
  const qs = subjectCode
    ? `?subject_code=${encodeURIComponent(subjectCode)}`
    : "";
  return apiFetch<{ items: TopicSummaryOut[]; total: number }>(
    `/api/v1/topics${qs}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function updateFact(
  factId: string,
  payload: FactUpdateRequest,
): Promise<FactOut> {
  return apiFetch<FactOut>(`/api/v1/facts/${encodeURIComponent(factId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listSubjects(
  signal?: AbortSignal,
): Promise<SubjectOut[]> {
  const data = await apiFetch<{ items: SubjectOut[] } | SubjectOut[]>(
    "/api/v1/subjects",
    {
      method: "GET",
      signal,
    },
  );
  return Array.isArray(data) ? data : data.items;
}
