export interface UserPreferences {
  default_exam_code: string;
  default_speed_challenge_seconds: number;
  reduced_motion: boolean;
  compact_mode: boolean;
}

export const DEFAULT_PREFERENCES: UserPreferences = {
  default_exam_code: "ssc_chsl_tier_1",
  default_speed_challenge_seconds: 35,
  reduced_motion: false,
  compact_mode: false,
};

export const PREFERENCES_STORAGE_KEY = "ai_exam_coach_preferences_v1";

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function clampSpeedChallengeSeconds(value: unknown): number {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) {
    return DEFAULT_PREFERENCES.default_speed_challenge_seconds;
  }
  return Math.max(5, Math.min(300, Math.round(num)));
}

export function normalizePreferences(raw: unknown): UserPreferences {
  if (typeof raw !== "object" || raw === null) {
    return { ...DEFAULT_PREFERENCES };
  }
  const obj = raw as Record<string, unknown>;
  const examCode =
    typeof obj.default_exam_code === "string" &&
    obj.default_exam_code.trim().length > 0
      ? obj.default_exam_code.trim()
      : DEFAULT_PREFERENCES.default_exam_code;

  return {
    default_exam_code: examCode,
    default_speed_challenge_seconds: clampSpeedChallengeSeconds(
      obj.default_speed_challenge_seconds,
    ),
    reduced_motion: Boolean(obj.reduced_motion),
    compact_mode: Boolean(obj.compact_mode),
  };
}

function getBrowserStorage(storage?: StorageLike | null): StorageLike | null {
  if (storage !== undefined) {
    return storage;
  }
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function loadPreferences(storage?: StorageLike | null): UserPreferences {
  const store = getBrowserStorage(storage);
  if (!store) {
    return { ...DEFAULT_PREFERENCES };
  }
  try {
    const raw = store.getItem(PREFERENCES_STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_PREFERENCES };
    }
    return normalizePreferences(JSON.parse(raw) as unknown);
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

export function savePreferences(
  prefs: UserPreferences,
  storage?: StorageLike | null,
): UserPreferences {
  const normalized = normalizePreferences(prefs);
  const store = getBrowserStorage(storage);
  if (store) {
    try {
      store.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(normalized));
    } catch {
      // Ignore storage quota errors
    }
  }
  applyDocumentPreferenceFlags(normalized);
  return normalized;
}

export function resetPreferences(
  storage?: StorageLike | null,
): UserPreferences {
  const store = getBrowserStorage(storage);
  if (store) {
    try {
      store.removeItem(PREFERENCES_STORAGE_KEY);
    } catch {
      // Ignore storage errors
    }
  }
  const defaults = { ...DEFAULT_PREFERENCES };
  applyDocumentPreferenceFlags(defaults);
  return defaults;
}

export function applyDocumentPreferenceFlags(prefs: UserPreferences): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (prefs.reduced_motion) {
    root.setAttribute("data-reduced-motion", "true");
  } else {
    root.removeAttribute("data-reduced-motion");
  }
  if (prefs.compact_mode) {
    root.setAttribute("data-compact", "true");
  } else {
    root.removeAttribute("data-compact");
  }
}


export const CUSTOM_AI_KEY_STORAGE_KEY = "ai_exam_coach_custom_ai_key_v1";

export function loadCustomAiKey(storage?: StorageLike | null): string {
  const store = getBrowserStorage(storage);
  if (!store) {
    return "";
  }
  try {
    return (store.getItem(CUSTOM_AI_KEY_STORAGE_KEY) ?? "").trim();
  } catch {
    return "";
  }
}

export function saveCustomAiKey(
  rawKey: string,
  storage?: StorageLike | null,
): string {
  const trimmed = rawKey.trim();
  const store = getBrowserStorage(storage);
  if (store) {
    try {
      if (trimmed.length > 0) {
        store.setItem(CUSTOM_AI_KEY_STORAGE_KEY, trimmed);
      } else {
        store.removeItem(CUSTOM_AI_KEY_STORAGE_KEY);
      }
    } catch {
      // Ignore storage errors
    }
  }
  return trimmed;
}

export function clearCustomAiKey(storage?: StorageLike | null): void {
  const store = getBrowserStorage(storage);
  if (store) {
    try {
      store.removeItem(CUSTOM_AI_KEY_STORAGE_KEY);
    } catch {
      // Ignore storage errors
    }
  }
}
