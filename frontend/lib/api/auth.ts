import { apiFetch } from "@/lib/api/client";

export const AUTH_TOKEN_STORAGE_KEY = "ai_exam_coach_auth_token_v1";

export interface AuthUserOut {
  id: string;
  email: string | null;
  display_name: string;
  auth_mode: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user: AuthUserOut;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const token = window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
    return token && token.trim().length > 0 ? token : null;
  } catch {
    return null;
  }
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  } catch {
    // Ignore storage errors
  }
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // Ignore storage errors
  }
}

export async function registerUser(
  payload: RegisterRequest,
): Promise<AuthTokenResponse> {
  const res = await apiFetch<AuthTokenResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setAuthToken(res.access_token);
  return res;
}

export async function loginUser(
  payload: LoginRequest,
): Promise<AuthTokenResponse> {
  const res = await apiFetch<AuthTokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setAuthToken(res.access_token);
  return res;
}

export async function getCurrentAuthUser(
  signal?: AbortSignal,
): Promise<AuthUserOut> {
  return apiFetch<AuthUserOut>("/api/v1/auth/me", {
    method: "GET",
    signal,
  });
}
