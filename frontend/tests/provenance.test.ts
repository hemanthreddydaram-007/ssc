import assert from "node:assert/strict";
import test from "node:test";

import {
  formatClassificationStatus,
  getProvenanceLabel,
  getReviewStatusLabel,
  isAiGeneratedExplanation,
  normalizeProvenance,
} from "../lib/utils/provenance";

test("normalizeProvenance maps known values and defaults unknown to unverified", () => {
  assert.equal(normalizeProvenance("extracted"), "extracted");
  assert.equal(normalizeProvenance("  PARAPHRASED "), "paraphrased");
  assert.equal(normalizeProvenance("ai_explanation"), "ai_explanation");
  assert.equal(normalizeProvenance("externally_verified"), "externally_verified");
  assert.equal(normalizeProvenance("made_up"), "unverified");
  assert.equal(normalizeProvenance(null), "unverified");
});

test("AI explanations are clearly distinguished from extracted source facts", () => {
  assert.equal(isAiGeneratedExplanation("ai_explanation"), true);
  assert.equal(isAiGeneratedExplanation("extracted"), false);
  assert.equal(isAiGeneratedExplanation("paraphrased"), false);

  assert.equal(getProvenanceLabel("extracted"), "Source-backed (Extracted)");
  assert.equal(getProvenanceLabel("ai_explanation"), "AI explanation");
  assert.equal(getProvenanceLabel(undefined), "Unverified");
});

test("review status and topic classification helpers format cleanly", () => {
  assert.equal(getReviewStatusLabel("verified"), "Verified");
  assert.equal(getReviewStatusLabel("conflict"), "Conflict");
  assert.equal(getReviewStatusLabel("needs_review"), "Needs review");
  assert.equal(getReviewStatusLabel(null), "Needs review");

  assert.equal(formatClassificationStatus("strong"), "Strong");
  assert.equal(formatClassificationStatus("needs_practice"), "Needs practice");
  assert.equal(formatClassificationStatus("developing"), "Developing");
  assert.equal(
    formatClassificationStatus("insufficient_data"),
    "Insufficient data",
  );
  assert.equal(formatClassificationStatus(undefined), "Insufficient data");
});
