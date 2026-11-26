import test from "node:test";
import assert from "node:assert/strict";

import { SECTION_CATALOG } from "../data/catalog.js";
import {
  EXAM_DURATION_SEC,
  OVERSPEED_DURATION_SEC,
  STABILIZE_DURATION_SEC,
  analyzeRun,
  computeAdaptiveTimer,
  evaluateCalibration,
  formatClock,
  formatDuration,
  parseQuestionFile,
  shuffleQuestions,
  validateQuestionSet
} from "../engine.js";

test("all 6 built-in sets have 25 valid, unambiguous PYQs each (150 total)", () => {
  const seenIds = new Set();
  let totalQuestions = 0;

  assert.equal(SECTION_CATALOG.length, 4);

  for (const section of SECTION_CATALOG) {
    for (const set of section.sets) {
      assert.equal(set.questions.length, 25, `${section.id}/${set.id} must have 25 questions`);
      for (const q of set.questions) {
        assert.ok(q.id && !seenIds.has(q.id), `Duplicate or missing id: ${q.id}`);
        seenIds.add(q.id);
        assert.equal(q.section, section.id);
        assert.ok(typeof q.topic === "string" && q.topic.length > 0);
        assert.ok(typeof q.prompt === "string" && q.prompt.length > 10);
        assert.ok(Array.isArray(q.options) && q.options.length === 4);
        assert.equal(new Set(q.options).size, 4, `Duplicate options in ${q.id}`);
        assert.ok(Number.isInteger(q.correctIndex) && q.correctIndex >= 0 && q.correctIndex <= 3);
        totalQuestions += 1;
      }
    }
  }

  assert.equal(totalQuestions, 150);
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
  assert.equal(res.netScore, 3.0);
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

  const highAtStandard = [
    { section: "Quant", mode: "exam", isRetry: false, isCustom: false, durationSec: 900, accuracyPct: 84 },
    { section: "Quant", mode: "exam", isRetry: false, isCustom: false, durationSec: 900, accuracyPct: 88 }
  ];
  assert.equal(computeAdaptiveTimer(highAtStandard, "Quant").durationSec, OVERSPEED_DURATION_SEC);

  const lowAccuracy = [
    { section: "English", mode: "exam", isRetry: false, isCustom: false, durationSec: 900, accuracyPct: 50 },
    { section: "English", mode: "exam", isRetry: false, isCustom: false, durationSec: 900, accuracyPct: 60 }
  ];
  assert.equal(computeAdaptiveTimer(lowAccuracy, "English").durationSec, STABILIZE_DURATION_SEC);

  const withCustomAndRetry = [
    ...highAtStandard,
    { section: "Quant", mode: "exam", isRetry: false, isCustom: true, durationSec: 900, accuracyPct: 10 },
    { section: "Quant", mode: "exam", isRetry: true, isCustom: false, durationSec: 360, accuracyPct: 10 }
  ];
  assert.equal(computeAdaptiveTimer(withCustomAndRetry, "Quant").durationSec, OVERSPEED_DURATION_SEC);
});

test("shuffleQuestions returns a non-mutating permutation", () => {
  const original = [{ id: "1" }, { id: "2" }, { id: "3" }, { id: "4" }];
  const shuffled = shuffleQuestions(original, () => 0.1);
  assert.notEqual(shuffled, original);
  assert.deepEqual(original.map((x) => x.id), ["1", "2", "3", "4"]);
  assert.deepEqual(shuffled.map((x) => x.id).sort(), ["1", "2", "3", "4"]);
});

test("validateQuestionSet validates custom JSON arrays, objects, and rejects malformed inputs", () => {
  const validArray = JSON.stringify([
    {
      prompt: "2 + 2 = ?",
      options: ["1", "2", "3", "4"],
      correctIndex: 3
    }
  ]);
  const res1 = validateQuestionSet(validArray, { defaultTitle: "Mini Drill" });
  assert.equal(res1.ok, true);
  assert.equal(res1.title, "Mini Drill");
  assert.equal(res1.questions[0].id, "custom-q1");
  assert.equal(res1.questions[0].topic, "General");

  const validWrapper = JSON.stringify({
    title: "Shift 4",
    section: "Quant",
    questions: [
      {
        id: "s4-1",
        topic: "Algebra",
        prompt: "x + 1 = 3",
        options: ["1", "2", "3", "4"],
        correctIndex: 1
      }
    ]
  });
  const res2 = validateQuestionSet(validWrapper);
  assert.equal(res2.ok, true);
  assert.equal(res2.title, "Shift 4");
  assert.equal(res2.section, "Quant");

  assert.equal(validateQuestionSet("{bad json").ok, false);
  assert.equal(validateQuestionSet("[]").ok, false);
  assert.equal(
    validateQuestionSet(
      JSON.stringify([{ prompt: "Q", options: ["A", "A", "C", "D"], correctIndex: 0 }])
    ).ok,
    false
  );
  assert.equal(
    validateQuestionSet(
      JSON.stringify([{ prompt: "Q", options: ["A", "B", "C", "D"], correctIndex: 5 }])
    ).ok,
    false
  );
});

test("parseQuestionFile handles .json and .csv files with quoted commas and letter answers", () => {
  const csvPayload =
    '\uFEFFid,topic,prompt,optionA,optionB,optionC,optionD,correctIndex\r\n' +
    'c1,Algebra,"If x + 1/x = 5, find x^2 + 1/x^2",21,23,25,27,B\r\n' +
    'c2,Series,"Next term: 2, 4, 8, ?",12,14,16,18,2\r\n';

  const parsedCsv = parseQuestionFile(csvPayload, { filename: "my-quant-drill.csv" });
  assert.equal(parsedCsv.ok, true);
  assert.equal(parsedCsv.title, "my-quant-drill");
  assert.equal(parsedCsv.questions.length, 2);
  assert.equal(parsedCsv.questions[0].prompt, "If x + 1/x = 5, find x^2 + 1/x^2");
  assert.equal(parsedCsv.questions[0].correctIndex, 1);
  assert.equal(parsedCsv.questions[1].correctIndex, 2);

  const parsedJson = parseQuestionFile(
    JSON.stringify([{ prompt: "Capital of India?", options: ["Mumbai", "Delhi", "Kolkata", "Chennai"], correctIndex: 1 }]),
    { filename: "gk-notes.json" }
  );
  assert.equal(parsedJson.ok, true);
  assert.equal(parsedJson.title, "gk-notes");

  assert.equal(parseQuestionFile("prompt,optionA\nonly,one", { filename: "bad.csv" }).ok, false);
  assert.equal(parseQuestionFile("", { filename: "empty.json" }).ok, false);
});
