export interface BackendHealthPayload {
  status: string;
  app: string;
  version: string;
  environment: string;
  auth_mode?: string;
  database: string;
  timestamp: string;
}

export type HealthCheckResult =
  | {
      kind: "ok";
      httpStatus: number;
      payload: BackendHealthPayload;
    }
  | {
      kind: "degraded";
      httpStatus: number;
      payload: BackendHealthPayload;
    }
  | {
      kind: "unreachable";
      errorMessage: string;
    };

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured && configured.length > 0) {
    return configured.replace(/\/+$/, "");
  }
  return "http://localhost:8000";
}

function isBackendHealthPayload(value: unknown): value is BackendHealthPayload {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.status === "string" &&
    typeof record.app === "string" &&
    typeof record.version === "string" &&
    typeof record.environment === "string" &&
    typeof record.database === "string" &&
    typeof record.timestamp === "string"
  );
}

/**
 * Query the FastAPI `/health` endpoint and return a discriminated status result
 * without throwing on HTTP 503 or network failures.
 */
export async function fetchBackendHealth(
  signal?: AbortSignal,
): Promise<HealthCheckResult> {
  const url = `${getApiBaseUrl()}/health`;
  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });

    const data: unknown = await response.json().catch(() => null);
    if (!isBackendHealthPayload(data)) {
      return {
        kind: "unreachable",
        errorMessage: `Unexpected response from /health (HTTP ${response.status})`,
      };
    }

    if (response.ok && data.status === "ok") {
      return {
        kind: "ok",
        httpStatus: response.status,
        payload: data,
      };
    }

    return {
      kind: "degraded",
      httpStatus: response.status,
      payload: data,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    const message =
      error instanceof Error
        ? error.message
        : "Unable to reach backend health endpoint";
    return {
      kind: "unreachable",
      errorMessage: message,
    };
  }
}
