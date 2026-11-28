/**
 * Safe numeric and priority normalization helpers for API payloads.
 * FastAPI / Pydantic v2 serializes Python `Decimal` fields as JSON strings
 * (e.g. `"50.00"`), and nullable fields may arrive as `null` or `undefined`.
 */

export function toNullableNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length === 0) {
      return null;
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function toNumber(value: unknown, fallback = 0): number {
  const parsed = toNullableNumber(value);
  return parsed !== null ? parsed : fallback;
}

export function formatPercent(
  value: unknown,
  digits = 1,
  nullLabel = "—",
): string {
  const parsed = toNullableNumber(value);
  if (parsed === null) {
    return nullLabel;
  }
  return `${parsed.toFixed(digits)}%`;
}

export function formatDecimal(value: unknown, maxFractionDigits = 2): string {
  const parsed = toNullableNumber(value);
  if (parsed === null) {
    return "0";
  }
  return parsed.toFixed(maxFractionDigits).replace(/\.?0+$/, "");
}

export type PriorityLevel = "high" | "medium" | "low";

/**
 * Normalize backend integer priority (1=high, 2=medium, >=3=low) or string
 * priority values into a consistent UI priority tier.
 */
export function normalizePriority(
  priority: number | string | null | undefined,
): PriorityLevel {
  if (typeof priority === "number" && Number.isFinite(priority)) {
    if (priority <= 1) return "high";
    if (priority === 2) return "medium";
    return "low";
  }
  if (typeof priority === "string") {
    const normalized = priority.trim().toLowerCase();
    if (normalized === "high") return "high";
    if (normalized === "medium") return "medium";
    if (normalized === "low") return "low";
    const asNum = Number(normalized);
    if (normalized.length > 0 && Number.isFinite(asNum)) {
      if (asNum <= 1) return "high";
      if (asNum === 2) return "medium";
      return "low";
    }
  }
  return "low";
}
