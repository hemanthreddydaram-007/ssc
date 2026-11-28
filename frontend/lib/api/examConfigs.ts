import { apiFetch } from "@/lib/api/client";

export interface ExamConfigJson {
  exam_code?: string;
  display_name?: string;
  subjects?: string[];
  question_types?: string[];
  supports_negative_marking?: boolean;
  timing_mode?: string[];
  default_speed_challenge_seconds?: number;
  notes?: string;
  [key: string]: unknown;
}

export interface ExamConfig {
  id: string;
  exam_code: string;
  name: string;
  version: string;
  config_json: ExamConfigJson;
  source_url: string | null;
  effective_from: string | null;
  effective_to: string | null;
  created_at: string;
}

type ExamConfigListResponse = ExamConfig[] | { items: ExamConfig[] };

export async function listExamConfigs(
  signal?: AbortSignal,
): Promise<ExamConfig[]> {
  const data = await apiFetch<ExamConfigListResponse>("/api/v1/exam-configs", {
    method: "GET",
    signal,
  });
  return Array.isArray(data) ? data : data.items;
}

export async function getExamConfig(
  examCode: string,
  signal?: AbortSignal,
): Promise<ExamConfig> {
  return apiFetch<ExamConfig>(
    `/api/v1/exam-configs/${encodeURIComponent(examCode)}`,
    {
      method: "GET",
      signal,
    },
  );
}

const SUBJECT_LABELS: Record<string, string> = {
  quantitative_aptitude: "Quantitative Aptitude / Maths",
  maths: "Quantitative Aptitude / Maths",
  reasoning: "General Intelligence / Reasoning",
  english: "English Language",
  general_awareness: "General Awareness",
};

export function formatSubjectLabel(code: string): string {
  return (
    SUBJECT_LABELS[code] ??
    code
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ")
  );
}

/**
 * Strip internal version tags like `(v1.0)` from exam pack display names.
 */
export function formatExamName(name: string): string {
  return name.replace(/\s*\(v?\d+(?:\.\d+)*\)\s*$/i, "").trim();
}
