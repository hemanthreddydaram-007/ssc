import { clearAuthToken, getAuthToken } from "@/lib/api/auth";
import { getApiBaseUrl } from "@/lib/api/health";
import { loadCustomAiKey } from "@/lib/utils/preferences";

export interface ApiErrorPayload {
  detail?: string;
  code?: string;
  existing_document_id?: string;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly existingDocumentId: string | undefined;
  readonly payload: ApiErrorPayload | null;

  constructor(
    message: string,
    status: number,
    payload: ApiErrorPayload | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = typeof payload?.code === "string" ? payload.code : undefined;
    this.existingDocumentId =
      typeof payload?.existing_document_id === "string"
        ? payload.existing_document_id
        : undefined;
    this.payload = payload;
  }
}

export function extractErrorMessage(
  payload: unknown,
  fallback: string,
): { message: string; objectPayload: ApiErrorPayload | null } {
  if (typeof payload === "object" && payload !== null) {
    const obj = payload as ApiErrorPayload;
    if (typeof obj.detail === "string" && obj.detail.trim().length > 0) {
      return { message: obj.detail, objectPayload: obj };
    }
    if (Array.isArray(obj.detail) && obj.detail.length > 0) {
      const first = obj.detail[0] as { msg?: unknown } | undefined;
      if (first && typeof first.msg === "string") {
        return { message: first.msg, objectPayload: obj };
      }
    }
    return { message: fallback, objectPayload: obj };
  }
  if (typeof payload === "string" && payload.trim().length > 0) {
    return { message: payload, objectPayload: null };
  }
  return { message: fallback, objectPayload: null };
}

export function handleUnauthorizedRedirect(): void {
  if (typeof window === "undefined") {
    return;
  }
  const path = window.location.pathname;
  if (path.startsWith("/login") || path.startsWith("/register")) {
    return;
  }
  clearAuthToken();
  const next = `${path}${window.location.search}`;
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = `${getApiBaseUrl()}${path}`;
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (
    init.body !== undefined &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const customAiKey = loadCustomAiKey();
  if (customAiKey && !headers.has("X-Gemini-Api-Key")) {
    headers.set("X-Gemini-Api-Key", customAiKey);
  }

  const response = await fetch(url, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (response.status === 401) {
    handleUnauthorizedRedirect();
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    const { message, objectPayload } = extractErrorMessage(
      parsed,
      `Request failed with HTTP ${response.status}`,
    );
    throw new ApiError(message, response.status, objectPayload);
  }

  return parsed as T;
}
