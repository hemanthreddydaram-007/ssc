export type CanonicalProvenance =
  | "extracted"
  | "paraphrased"
  | "ai_explanation"
  | "externally_verified"
  | "unverified";

export function normalizeProvenance(raw: string | null | undefined): CanonicalProvenance {
  switch ((raw ?? "").trim().toLowerCase()) {
    case "extracted":
      return "extracted";
    case "paraphrased":
      return "paraphrased";
    case "ai_explanation":
      return "ai_explanation";
    case "externally_verified":
      return "externally_verified";
    default:
      return "unverified";
  }
}

export function isAiGeneratedExplanation(raw: string | null | undefined): boolean {
  return normalizeProvenance(raw) === "ai_explanation";
}

export function getProvenanceLabel(raw: string | null | undefined): string {
  switch (normalizeProvenance(raw)) {
    case "extracted":
      return "Source-backed (Extracted)";
    case "paraphrased":
      return "Source-backed (Paraphrased)";
    case "ai_explanation":
      return "AI explanation";
    case "externally_verified":
      return "Externally verified";
    case "unverified":
      return "Unverified";
  }
}

export function getReviewStatusLabel(raw: string | null | undefined): string {
  switch ((raw ?? "").trim().toLowerCase()) {
    case "verified":
      return "Verified";
    case "conflict":
      return "Conflict";
    case "rejected":
      return "Rejected";
    case "failed_review":
      return "Failed review";
    default:
      return "Needs review";
  }
}

export function formatClassificationStatus(raw: string | null | undefined): string {
  switch ((raw ?? "").trim().toLowerCase()) {
    case "strong":
      return "Strong";
    case "needs_practice":
      return "Needs practice";
    case "developing":
      return "Developing";
    case "insufficient_data":
    default:
      return "Insufficient data";
  }
}
