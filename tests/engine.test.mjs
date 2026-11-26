import test from "node:test";
import assert from "node:assert/strict";

import quantQuestions from "../data/quant-set-1.js";
import reasonQuestions from "../data/reason-set-1.js";
import {
  EXAM_DURATION_SEC,
  OVERSPEED_DURATION_SEC,
  STABILIZE_DURATION_SEC,
  analyzeRun,
  computeAdaptiveTimer,
  evaluateCalibration,
  formatClock,
  formatDuration
} from "../engine.js";

test("question banks have 25 valid, unambiguous PYQs each", () => {
  const banks = [
    { name: "Quant", list: quantQuestions },
    { name: "Reasoning", list: reasonQuestions }
  ];
  const seenIds = new Set();

  for (const bank of banks) {
    assert.equal(bank.list.length, 25, `${bank.name} must have 25 questions`);
    for (const q of bank.list) {
      assert.ok(q.id && !seenIds.has(q.id), `Duplicate or missing id: ${q.id}`);
      seenIds.add(q.id);
      assert.equal(q.section, bank.name);
      assert.ok(typeof q.topic === "string" && q.topic.length > 0);
      assert.ok(typeof q.prompt === "string" && q.prompt.length > 10);
      assert.ok(Array.isArray(q.options) && q.options.length === 4);
      assert.equal(new Set(q.options).size, 4, `Duplicate options in ${q.id}`);
      assert.ok(Number.isInteger(q.correctIndex) && q.correctIndex >= 0 && q.correctIndex <= 3);
    }
  }
});

test("formatClock and formatDuration handle boundary values cleanly", () => {
  assert.equal(formatClock(900_000), "15:00");
  assert.equal(formatClock(899_100), "15:00");
  assert.equal(formatClock(60_000), "01:00");
  assert.equal(formatClock(100), "00:01");
  assert.equal(formatClock(0), "00:00");
  assert.equal(formatClock(-500), "00:00");

  assert.equal(formatDuration(36_000), "36.0s");
  assert.equal(formatDuration(36_200), "36.2s");
  assert.equal(formatDuration(59_800), "59.8s");
  assert.equal(formatDuration(82_000), "1m 22s");
});

test("analyzeRun classifies quadrants, panic errors, opportunity cost, and weak PYQs", () => {
  const sampleQuestions = [
    { id: "q1", section: "Quant", topic: "T1", prompt: "P1", options: ["A", "B", "C", "D"], correctIndex: 0 },
    { id: "q2", section: "Quant", topic: "T2", prompt: "P2", options: ["A", "B", "C", "D"], correctIndex: 1 },
    { id: "q3", section: "Quant", topic: "T3", prompt: "P3", options: ["A", "B", "C", "D"], correctIndex: 2 },
    { id: "q4", section: "Quant", topic: "T4", prompt: "P4", options: ["A", "B", "C", "D"], correctIndex: 3 },
    { id: "q5", section: "Quant", topic: "T5", prompt: "P5", options: ["A", "B", "C", "D"], correctIndex: 0 },
    { id: "q6", section: "Quant", topic: "T6", prompt: "P6", options: ["A", "B", "C", "D"], correctIndex: 1 }
  ];

  // q1: Fast & Right (exactly 36s -> <=36s)
  // q2: Slow & Right (45s), answered in last 60s (NOT panic because it's right!)
  // q3: Fast & Wrong (12s), answered in last 60s -> PANIC ERROR
  // q4: Slow & Wrong (72s), answered early (500s left) -> Score Killer, 72/36 = 2.0 lost
  // q5: Unattempted fast (8s) -> NOT weak
  // q6: Unattempted slow (40s) -> weak (>36s)
  const answers = [0, 1, 0, 0, null, null];
  const telemetry = [
    { totalMs: 36_000, visits: 1, savedRemainingMs: 700_000 },
    { totalMs: 45_000, visits: 2, savedRemainingMs: 40_000 },
    { totalMs: 12_000, visits: 1, savedRemainingMs: 15_000 },
    { totalMs: 72_000, visits: 3, savedRemainingMs: 500_000 },
    { totalMs: 8_000, visits: 1, savedRemainingMs: null },
    { totalMs: 40_000, visits: 1, savedRemainingMs: null }
  ];

  const res = analyzeRun({
    questions: sampleQuestions,
    answers,
    telemetry,
    durationSec: 900,
    totalElapsedMs: 213_000
  });

  assert.equal(res.correctCount, 2);
  assert.equal(res.wrongCount, 2);
  assert.equal(res.unattemptedCount, 2);
  assert.equal(res.netScore, 3.0); // 2*2 - 2*0.5 = 3.0
  assert.equal(res.accuracyPct, 50.0);

  assert.deepEqual(res.quadrants.fastRight.map((i) => i.number), [1]);
  assert.deepEqual(res.quadrants.slowRight.map((i) => i.number), [2]);
  assert.deepEqual(res.quadrants.fastWrong.map((i) => i.number), [3]);
  assert.deepEqual(res.quadrants.slowWrong.map((i) => i.number), [4]);
  assert.deepEqual(res.quadrants.unattempted.map((i) => i.number), [5, 6]);

  assert.deepEqual(res.panicErrors.map((i) => i.number), [3]);
  assert.equal(res.slowWrongTotalSec, 72);
  assert.equal(res.opportunityCostAttempts, 2.0);
  assert.equal(res.slowestItem.number, 4);

  // Weak PYQs = Slow & Right (2), Fast & Wrong (3), Slow & Wrong (4), Slow Unattempted (6)
  assert.deepEqual(res.weakQuestions.map((q) => q.id), ["q2", "q3", "q4", "q6"]);
});

test("evaluateCalibration formats truth and detects match/mismatch", () => {
  const slowest = { totalMs: 82_000, visits: 2 };
  const miss = evaluateCalibration(slowest, "under30");
  assert.equal(miss.matched, false);
  assert.equal(miss.summaryText, "You guessed Under 30s. Reality: 1m 22s across 2 visits.");

  const hit = evaluateCalibration({ totalMs: 45_000, visits: 1 }, "30to60");
  assert.equal(hit.matched, true);
  assert.equal(hit.summaryText, "You guessed 30s–60s. Reality: 45.0s across 1 visit.");
});

test("computeAdaptiveTimer scales 17:00 / 15:00 / 13:30 from last 2 full exam runs", () => {
  assert.equal(computeAdaptiveTimer([], "Quant").durationSec, EXAM_DURATION_SEC);

  const singleRun = [
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 90 }
  ];
  assert.equal(computeAdaptiveTimer(singleRun, "Quant").durationSec, EXAM_DURATION_SEC);

  const lowAccuracy = [
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 50 },
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 60 }
  ];
  assert.equal(computeAdaptiveTimer(lowAccuracy, "Quant").durationSec, STABILIZE_DURATION_SEC);

  const midAccuracy = [
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 70 },
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 76 }
  ];
  assert.equal(computeAdaptiveTimer(midAccuracy, "Quant").durationSec, EXAM_DURATION_SEC);

  const highAtStandard = [
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 84 },
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 88 }
  ];
  assert.equal(computeAdaptiveTimer(highAtStandard, "Quant").durationSec, OVERSPEED_DURATION_SEC);

  // If >80% was achieved at 17:00, step down to 15:00 rather than jumping straight to 13:30
  const highAt17 = [
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 1020, accuracyPct: 88 },
    { section: "Quant", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 88 }
  ];
  assert.equal(computeAdaptiveTimer(highAt17, "Quant").durationSec, EXAM_DURATION_SEC);

  // Retry and Gate runs must be ignored for adaptive scaling
  const withNoise = [
    ...highAtStandard,
    { section: "Quant", mode: "gate", isRetry: false, durationSec: 900, accuracyPct: 20 },
    { section: "Quant", mode: "exam", isRetry: true, durationSec: 360, accuracyPct: 20 },
    { section: "Reasoning", mode: "exam", isRetry: false, durationSec: 900, accuracyPct: 30 }
  ];
  assert.equal(computeAdaptiveTimer(withNoise, "Quant").durationSec, OVERSPEED_DURATION_SEC);
});
