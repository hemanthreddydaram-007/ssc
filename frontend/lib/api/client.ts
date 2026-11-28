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

export const DEFAULT_COLD_START_RETRY_DELAYS_MS = [1500, 3000] as const;
const RETRYABLE_COLD_START_STATUSES = new Set([502, 503, 504]);

export function shouldRetryColdStartRequest(
  path: string,
  method?: string,
): boolean {
  const normalizedMethod = (method ?? "GET").toUpperCase();
  if (normalizedMethod === "GET" || normalizedMethod === "HEAD") {
    return true;
  }
  const pathname = path.split("?")[0];
  return normalizedMethod === "POST" && pathname === "/api/v1/auth/login";
}

function waitForRetryDelay(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("The operation was aborted.", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("The operation was aborted.", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  retryDelaysMs: readonly number[] = DEFAULT_COLD_START_RETRY_DELAYS_MS,
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

  const canRetry = shouldRetryColdStartRequest(path, init.method);
  const maxRetries = canRetry ? retryDelaysMs.length : 0;

  let response: Response | null = null;
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      response = await fetch(url, {
        ...init,
        headers,
        cache: "no-store",
      });
      if (
        RETRYABLE_COLD_START_STATUSES.has(response.status) &&
        attempt < maxRetries
      ) {
        const contentType = response.headers.get("content-type") ?? "";
        // Gateway spin-up errors are typically plain/HTML, whereas FastAPI app errors return JSON.
        if (!contentType.includes("application/json")) {
          await waitForRetryDelay(retryDelaysMs[attempt] ?? 1500, init.signal);
          continue;
        }
      }
      break;
    } catch (error) {
      if (
        error instanceof DOMException &&
        error.name === "AbortError"
      ) {
        throw error;
      }
      if (error instanceof TypeError && attempt < maxRetries) {
        await waitForRetryDelay(retryDelaysMs[attempt] ?? 1500, init.signal);
        continue;
      }
      throw error;
    }
  }

  if (!response) {
    throw new TypeError("Failed to fetch");
  }

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
