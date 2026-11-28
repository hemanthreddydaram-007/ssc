import { getAuthToken } from "@/lib/api/auth";
import {
  ApiError,
  apiFetch,
  extractErrorMessage,
  handleUnauthorizedRedirect,
} from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/api/health";

export type DocumentSourceType = "pdf" | "image" | "plain_text";

export type MaterialType =
  | "notes"
  | "textbook"
  | "pyq"
  | "question_bank"
  | "current_affairs"
  | "other";

export const MATERIAL_TYPE_OPTIONS: readonly {
  value: MaterialType;
  label: string;
}[] = [
  { value: "notes", label: "Study Notes" },
  { value: "textbook", label: "Textbook / Chapter" },
  { value: "pyq", label: "Previous-Year Paper (PYQ)" },
  { value: "question_bank", label: "Question Bank" },
  { value: "current_affairs", label: "Current Affairs" },
  { value: "other", label: "Other Material" },
] as const;

export const LANGUAGE_OPTIONS: readonly { value: string; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "bilingual", label: "Bilingual (English + Hindi)" },
] as const;

export interface DocumentItem {
  id: string;
  user_id: string;
  title: string;
  original_filename: string;
  source_type: DocumentSourceType | string;
  mime_type: string;
  file_size_bytes: number;
  sha256: string;
  exam_config_id: string | null;
  subject_code: string | null;
  detected_subject_code: string | null;
  classification_confidence: number | null;
  chapter_or_topic_hint: string | null;
  material_type: string;
  language: string;
  source_label: string | null;
  page_count: number;
  status: string;
  extraction_version?: string | null;
  coverage_summary_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentListQuery {
  subject_code?: string;
  material_type?: string;
  status?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface DocumentMetadataFields {
  title?: string;
  exam_config_id?: string | null;
  subject_code?: string | null;
  chapter_or_topic_hint?: string | null;
  material_type?: string;
  language?: string;
  source_label?: string | null;
}

export interface UploadDocumentParams extends DocumentMetadataFields {
  file: File;
  allow_duplicate?: boolean;
  onProgress?: (percent: number) => void;
}

export interface CreateTextDocumentParams extends DocumentMetadataFields {
  title: string;
  content: string;
  allow_duplicate?: boolean;
}

export interface DeleteDocumentResponse {
  deleted_id: string;
  storage_removed: boolean;
}

export interface DocumentAssetOut {
  id: string;
  page_number: number;
  asset_type: string;
  mime_type: string;
  width: number;
  height: number;
}

export interface DocumentPageOut {
  id: string;
  page_number: number;
  extracted_text: string;
  extraction_method: string;
  confidence: number;
  processing_status: string;
  needs_ocr: boolean;
  ocr_provider: string | null;
  raw_char_count: number;
  image_count: number;
  table_count: number;
  tables_json: unknown[] | null;
  warning: string | null;
  assets: DocumentAssetOut[];
}

export interface DocumentPagesResponse {
  document_id: string;
  page_count: number;
  items: DocumentPageOut[];
}

export interface LowConfidencePageOut {
  page_number: number;
  confidence: number;
  extraction_method: string;
  warning: string | null;
}

export interface CoverageAuditOut {
  document_id: string;
  total_pages: number;
  pages_extracted_text: number;
  pages_extracted_ocr: number;
  pages_requiring_ocr: number;
  pages_not_processed: number;
  low_confidence_pages: LowConfidencePageOut[];
  tables_extracted: number;
  images_extracted: number;
  chunks_created: number;
  facts_extracted: number;
  concepts_identified: number;
  questions_extracted: number;
  records_rejected_or_uncertain: number;
  low_confidence_topics: string[];
}

export async function listDocuments(
  query: DocumentListQuery = {},
  signal?: AbortSignal,
): Promise<DocumentListResponse> {
  const params = new URLSearchParams();
  if (query.subject_code) params.set("subject_code", query.subject_code);
  if (query.material_type) params.set("material_type", query.material_type);
  if (query.status) params.set("status", query.status);
  if (query.q && query.q.trim().length > 0) params.set("q", query.q.trim());
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));

  const qs = params.toString();
  return apiFetch<DocumentListResponse>(
    `/api/v1/documents${qs ? `?${qs}` : ""}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function getDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentItem> {
  return apiFetch<DocumentItem>(
    `/api/v1/documents/${encodeURIComponent(documentId)}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function updateDocumentMetadata(
  documentId: string,
  payload: DocumentMetadataFields,
): Promise<DocumentItem> {
  return apiFetch<DocumentItem>(
    `/api/v1/documents/${encodeURIComponent(documentId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteDocument(
  documentId: string,
  cascadeDerived = true,
): Promise<DeleteDocumentResponse> {
  const params = new URLSearchParams({
    cascade_derived: String(cascadeDerived),
  });
  return apiFetch<DeleteDocumentResponse>(
    `/api/v1/documents/${encodeURIComponent(documentId)}?${params.toString()}`,
    {
      method: "DELETE",
    },
  );
}

export async function getDocumentPages(
  documentId: string,
  needsOcrOnly = false,
  signal?: AbortSignal,
): Promise<DocumentPagesResponse> {
  const params = new URLSearchParams({
    needs_ocr_only: String(needsOcrOnly),
  });
  return apiFetch<DocumentPagesResponse>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/pages?${params.toString()}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function getDocumentCoverage(
  documentId: string,
  signal?: AbortSignal,
): Promise<CoverageAuditOut> {
  return apiFetch<CoverageAuditOut>(
    `/api/v1/documents/${encodeURIComponent(documentId)}/coverage`,
    {
      method: "GET",
      signal,
    },
  );
}

export function getDocumentAssetUrl(
  documentId: string,
  assetId: string,
): string {
  return `${getApiBaseUrl()}/api/v1/documents/${encodeURIComponent(documentId)}/assets/${encodeURIComponent(assetId)}`;
}

export async function createTextDocument(
  payload: CreateTextDocumentParams,
): Promise<DocumentItem> {
  return apiFetch<DocumentItem>("/api/v1/documents/text", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Upload a PDF or image via XMLHttpRequest to report real byte-transfer progress.
 */
export function uploadDocumentFile(
  params: UploadDocumentParams,
): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append("file", params.file);
  if (params.title && params.title.trim().length > 0) {
    formData.append("title", params.title.trim());
  }
  if (params.exam_config_id) {
    formData.append("exam_config_id", params.exam_config_id);
  }
  if (params.subject_code) {
    formData.append("subject_code", params.subject_code);
  }
  if (
    params.chapter_or_topic_hint &&
    params.chapter_or_topic_hint.trim().length > 0
  ) {
    formData.append(
      "chapter_or_topic_hint",
      params.chapter_or_topic_hint.trim(),
    );
  }
  if (params.material_type) {
    formData.append("material_type", params.material_type);
  }
  if (params.language) {
    formData.append("language", params.language);
  }
  if (params.source_label && params.source_label.trim().length > 0) {
    formData.append("source_label", params.source_label.trim());
  }
  if (params.allow_duplicate !== undefined) {
    formData.append("allow_duplicate", String(params.allow_duplicate));
  }

  return new Promise<DocumentItem>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${getApiBaseUrl()}/api/v1/documents`, true);
    xhr.setRequestHeader("Accept", "application/json");
    const token = getAuthToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0 && params.onProgress) {
        const pct = Math.min(100, Math.round((event.loaded / event.total) * 100));
        params.onProgress(pct);
      }
    };

    xhr.onload = () => {
      let parsed: unknown = null;
      if (xhr.responseText.length > 0) {
        try {
          parsed = JSON.parse(xhr.responseText) as unknown;
        } catch {
          parsed = xhr.responseText;
        }
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        params.onProgress?.(100);
        resolve(parsed as DocumentItem);
        return;
      }

      if (xhr.status === 401) {
        handleUnauthorizedRedirect();
      }

      const { message, objectPayload } = extractErrorMessage(
        parsed,
        `Upload failed with HTTP ${xhr.status}`,
      );
      reject(new ApiError(message, xhr.status, objectPayload));
    };

    xhr.onerror = () => {
      reject(
        new ApiError(
          "Upload connection was interrupted before the server responded. For very large PDFs (>25 MB), try compressing or splitting by chapter, or retry once the server finishes waking up.",
          0,
        ),
      );
    };

    xhr.onabort = () => {
      reject(new ApiError("Document upload was cancelled", 0));
    };

    xhr.send(formData);
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(2)} MB`;
}
