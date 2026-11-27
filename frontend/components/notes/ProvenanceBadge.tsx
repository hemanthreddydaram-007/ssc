import { Badge } from "@/components/ui/badge";
import {
  getProvenanceLabel,
  getReviewStatusLabel,
  normalizeProvenance,
} from "@/lib/utils/provenance";

interface ProvenanceBadgeProps {
  provenance: string;
  reviewStatus?: string;
}

export function ProvenanceBadge({
  provenance,
  reviewStatus,
}: ProvenanceBadgeProps) {
  const normalizedProv = normalizeProvenance(provenance);
  const normalizedReview = reviewStatus?.toLowerCase();
  const label = getProvenanceLabel(normalizedProv);

  const provenanceEl = (() => {
    switch (normalizedProv) {
      case "extracted":
      case "externally_verified":
        return <Badge variant="success">{label}</Badge>;
      case "paraphrased":
        return <Badge variant="secondary">{label}</Badge>;
      case "ai_explanation":
        return <Badge variant="outline">{label}</Badge>;
      case "unverified":
      default:
        return <Badge variant="warning">{label}</Badge>;
    }
  })();

  const reviewEl = (() => {
    if (!normalizedReview || normalizedReview === "verified") {
      return null;
    }
    const reviewLabel = getReviewStatusLabel(normalizedReview);
    if (normalizedReview === "conflict") {
      return <Badge variant="destructive">{reviewLabel}</Badge>;
    }
    return <Badge variant="warning">{reviewLabel}</Badge>;
  })();

  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {provenanceEl}
      {reviewEl}
    </span>
  );
}
