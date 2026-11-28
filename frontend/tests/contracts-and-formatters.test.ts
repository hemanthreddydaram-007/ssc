import assert from "node:assert/strict";
import test from "node:test";

import {
  formatDurationMs,
  getAttemptId,
  getOptionKey,
  getOptionText,
  isPaletteItemAnswered,
  type AttemptSummaryOut,
  type PaletteItemOut,
} from "../lib/api/attempts";
import { formatExamName } from "../lib/api/examConfigs";
import {
  formatJobStageLabel,
  formatJobTypeTitle,
  isTerminalJobStatus,
} from "../lib/api/jobs";
import {
  formatDecimal,
  formatPercent,
  normalizePriority,
  toNullableNumber,
  toNumber,
} from "../lib/utils/number";

test("toNumber and toNullableNumber handle numbers, Decimal strings, and nullish values safely", () => {
  assert.equal(toNullableNumber(42.5), 42.5);
  assert.equal(toNullableNumber("50.00"), 50);
  assert.equal(toNullableNumber("  -12.75 "), -12.75);
  assert.equal(toNullableNumber(0), 0);
  assert.equal(toNullableNumber("0.00"), 0);

  assert.equal(toNullableNumber(null), null);
  assert.equal(toNullableNumber(undefined), null);
  assert.equal(toNullableNumber(""), null);
  assert.equal(toNullableNumber("   "), null);
  assert.equal(toNullableNumber("not-a-number"), null);
  assert.equal(toNullableNumber(Number.NaN), null);
  assert.equal(toNullableNumber(Number.POSITIVE_INFINITY), null);

  assert.equal(toNumber("87.50"), 87.5);
  assert.equal(toNumber(null), 0);
  assert.equal(toNumber(undefined, -1), -1);
  assert.equal(toNumber("bad", 99), 99);
});

test("formatPercent, formatDecimal, and formatDurationMs handle Pydantic Decimal strings", () => {
  assert.equal(formatPercent("50.00"), "50.0%");
  assert.equal(formatPercent(66.666, 2), "66.67%");
  assert.equal(formatPercent(null), "—");
  assert.equal(formatPercent(undefined, 1, "N/A"), "N/A");

  assert.equal(formatDecimal("12.50"), "12.5");
  assert.equal(formatDecimal("10.00"), "10");
  assert.equal(formatDecimal(null), "0");

  assert.equal(formatDurationMs(0), "0s");
  assert.equal(formatDurationMs("45000"), "45s");
  assert.equal(formatDurationMs(125_000), "2m 05s");
  assert.equal(formatDurationMs(null), "0s");
});

test("getOptionKey and getOptionText support both active-test and question-bank shapes", () => {
  assert.equal(getOptionKey({ key: "A", text: "20%" }), "A");
  assert.equal(getOptionText({ key: "A", text: "20%" }), "20%");

  assert.equal(
    getOptionKey({ option_key: "B", option_text: "25%" }),
    "B",
  );
  assert.equal(
    getOptionText({ option_key: "B", option_text: "25%" }),
    "25%",
  );

  // Question-bank option_key/option_text takes precedence if both present
  assert.equal(
    getOptionKey({ key: "A", option_key: "C", text: "old", option_text: "new" }),
    "C",
  );
  assert.equal(
    getOptionText({ key: "A", option_key: "C", text: "old", option_text: "new" }),
    "new",
  );

  assert.equal(getOptionKey({}), "");
  assert.equal(getOptionText({}), "");
});

test("getAttemptId resolves attempt_id with fallback to id", () => {
  const base: Omit<AttemptSummaryOut, "attempt_id"> = {
    test_id: "test-1",
    timer_mode: "speed_challenge",
    status: "submitted",
    started_at: "2026-11-28T00:00:00Z",
    submitted_at: "2026-11-28T00:05:00Z",
    total_score: "8.00",
    max_score: "10.00",
    total_time_ms: 42_000,
    correct_count: 4,
    incorrect_count: 1,
    skipped_count: 0,
    timed_out_count: 0,
  };

  assert.equal(
    getAttemptId({ ...base, attempt_id: "att-123", id: "legacy-id" }),
    "att-123",
  );
  assert.equal(
    getAttemptId({
      ...base,
      attempt_id: undefined as unknown as string,
      id: "legacy-456",
    }),
    "legacy-456",
  );
  assert.equal(
    getAttemptId({ ...base, attempt_id: undefined as unknown as string }),
    "",
  );
});

test("isPaletteItemAnswered handles backend selected_option_key, status, and legacy has_answer", () => {
  const mkItem = (overrides: Partial<PaletteItemOut>): PaletteItemOut => ({
    index: 0,
    test_question_id: "tq-1",
    status: "unvisited",
    is_marked_for_review: false,
    ...overrides,
  });

  assert.equal(isPaletteItemAnswered(mkItem({ status: "unvisited" })), false);
  assert.equal(
    isPaletteItemAnswered(
      mkItem({ status: "skipped", selected_option_key: null }),
    ),
    false,
  );
  assert.equal(
    isPaletteItemAnswered(
      mkItem({ status: "timed_out", selected_option_key: null }),
    ),
    false,
  );

  // Backend sends selected_option_key and status="answered" without has_answer
  assert.equal(
    isPaletteItemAnswered(
      mkItem({ status: "answered", selected_option_key: "B" }),
    ),
    true,
  );
  assert.equal(
    isPaletteItemAnswered(
      mkItem({ status: "unvisited", selected_option_key: "A" }),
    ),
    true,
  );
  assert.equal(isPaletteItemAnswered(mkItem({ has_answer: true })), true);
});

test("normalizePriority maps backend integer priorities and string labels accurately", () => {
  assert.equal(normalizePriority(1), "high");
  assert.equal(normalizePriority(0), "high");
  assert.equal(normalizePriority(2), "medium");
  assert.equal(normalizePriority(3), "low");
  assert.equal(normalizePriority(4), "low");

  assert.equal(normalizePriority("1"), "high");
  assert.equal(normalizePriority("2"), "medium");
  assert.equal(normalizePriority("5"), "low");

  assert.equal(normalizePriority("high"), "high");
  assert.equal(normalizePriority(" MEDIUM "), "medium");
  assert.equal(normalizePriority("low"), "low");
  assert.equal(normalizePriority(null), "low");
  assert.equal(normalizePriority(undefined), "low");
  assert.equal(normalizePriority("unknown"), "low");
});

test("job label formatters and formatExamName format user-facing labels cleanly", () => {
  assert.equal(formatJobTypeTitle("extract_only"), "Extracting Document Pages");
  assert.equal(
    formatJobTypeTitle("extract_knowledge"),
    "AI Knowledge & Question Extraction",
  );
  assert.equal(formatJobTypeTitle("generate_notes"), "Generating Smart Notes");
  assert.equal(
    formatJobStageLabel("page_extraction"),
    "Reading pages & tables",
  );
  assert.equal(isTerminalJobStatus("completed"), true);
  assert.equal(isTerminalJobStatus("failed"), true);
  assert.equal(isTerminalJobStatus("running"), false);
  assert.equal(isTerminalJobStatus("queued"), false);

  assert.equal(formatExamName("SSC CHSL Tier 1 (v1.0)"), "SSC CHSL Tier 1");
  assert.equal(formatExamName("SSC CGL Tier 1"), "SSC CGL Tier 1");
});
