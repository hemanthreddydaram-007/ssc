import test from "node:test";
import assert from "node:assert/strict";

import { SECTION_CATALOG } from "../data/catalog.js";
import {
  QUESTION_TIME_LIMIT_MS,
  QUESTION_TIME_LIMIT_SEC,
  analyzeRun,
  findNextAvailableIndex,
  formatQuestionSeconds,
  getQuestionRemainingMs,
  parseQuestionFile,
  parseTxtQuestionPaper,
  resolveTimeoutTransition,
  shuffleQuestions,
  validateQuestionSet
} from "../engine.js";
import {
  buildOfflineMixedSet,
  buildOfflineVariantSet,
  collectFilteredQuestions,
  generateQuestionsWithGemini,
  getAvailableSections,
  getAvailableTopics
} from "../generator.js";

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

test("formatQuestionSeconds and getQuestionRemainingMs track cumulative 35s budget accurately", () => {
  assert.equal(QUESTION_TIME_LIMIT_SEC, 35);
  assert.equal(QUESTION_TIME_LIMIT_MS, 35_000);
  assert.equal(formatQuestionSeconds(35_000), "35s");
  assert.equal(formatQuestionSeconds(34_001), "35s");
  assert.equal(formatQuestionSeconds(34_000), "34s");
  assert.equal(formatQuestionSeconds(100), "1s");
  assert.equal(formatQuestionSeconds(0), "0s");
  assert.equal(formatQuestionSeconds(-250), "0s");

  assert.equal(
    getQuestionRemainingMs({ totalMs: 0, activeEnteredAt: 1_000, now: 11_000 }),
    25_000
  );
  assert.equal(
    getQuestionRemainingMs({ totalMs: 12_000, activeEnteredAt: 50_000, now: 65_000 }),
    8_000
  );
  assert.equal(
    getQuestionRemainingMs({ totalMs: 20_000, activeEnteredAt: 10_000, now: 30_000 }),
    0
  );
});

test("analyzeRun scores (+2 / -0.50), groups correct/wrong/unattempted, and extracts missed PYQs", () => {
  const sampleQuestions = [
    { id: "q1", section: "Quant", topic: "T1", prompt: "P1", options: ["A", "B", "C", "D"], correctIndex: 0 },
    { id: "q2", section: "Quant", topic: "T2", prompt: "P2", options: ["A", "B", "C", "D"], correctIndex: 1 },
    { id: "q3", section: "Quant", topic: "T3", prompt: "P3", options: ["A", "B", "C", "D"], correctIndex: 2 },
    { id: "q4", section: "Quant", topic: "T4", prompt: "P4", options: ["A", "B", "C", "D"], correctIndex: 3 },
    { id: "q5", section: "Quant", topic: "T5", prompt: "P5", options: ["A", "B", "C", "D"], correctIndex: 0 }
  ];

  const answers = [0, 1, 0, null, null];
  const res = analyzeRun({ questions: sampleQuestions, answers });

  assert.equal(res.totalQuestions, 5);
  assert.equal(res.attemptedCount, 3);
  assert.equal(res.correctCount, 2);
  assert.equal(res.wrongCount, 1);
  assert.equal(res.unattemptedCount, 2);
  assert.equal(res.netScore, 3.5);
  assert.equal(res.maxScore, 10);
  assert.equal(res.accuracyPct, 66.7);

  assert.deepEqual(res.groups.correct.map((i) => i.number), [1, 2]);
  assert.deepEqual(res.groups.wrong.map((i) => i.number), [3]);
  assert.deepEqual(res.groups.unattempted.map((i) => i.number), [4, 5]);
  assert.deepEqual(res.missedQuestions.map((q) => q.id), ["q3", "q4", "q5"]);
});

test("findNextAvailableIndex skips expired questions and handles single/exhausted sets", () => {
  assert.equal(
    findNextAvailableIndex({ currentIndex: 0, totalQuestions: 1, expired: [false] }),
    null
  );
  assert.equal(
    findNextAvailableIndex({ currentIndex: 0, totalQuestions: 4, expired: [false, true, false, false] }),
    2
  );
  assert.equal(
    findNextAvailableIndex({ currentIndex: 3, totalQuestions: 4, expired: [true, false, true, false] }),
    1
  );
  assert.equal(
    findNextAvailableIndex({ currentIndex: 2, totalQuestions: 4, expired: [true, true, false, true] }),
    null
  );
});

test("resolveTimeoutTransition advances to next question and finishes on last question", () => {
  assert.deepEqual(
    resolveTimeoutTransition({
      currentIndex: 0,
      totalQuestions: 3,
      expired: [true, false, false],
      visited: [true, false, false],
      answers: [null, null, null]
    }),
    { action: "next", nextIndex: 1 }
  );

  assert.deepEqual(
    resolveTimeoutTransition({
      currentIndex: 2,
      totalQuestions: 3,
      expired: [true, false, true],
      visited: [true, true, true],
      answers: [null, 1, null]
    }),
    { action: "finish" }
  );

  assert.deepEqual(
    resolveTimeoutTransition({
      currentIndex: 2,
      totalQuestions: 3,
      expired: [false, false, true],
      visited: [true, false, true],
      answers: [0, null, null]
    }),
    { action: "next", nextIndex: 1 }
  );
});

test("shuffleQuestions returns a non-mutating permutation", () => {
  const original = [{ id: "1" }, { id: "2" }, { id: "3" }, { id: "4" }];
  const shuffled = shuffleQuestions(original, () => 0.1);
  assert.notEqual(shuffled, original);
  assert.deepEqual(original.map((x) => x.id), ["1", "2", "3", "4"]);
  assert.deepEqual(shuffled.map((x) => x.id).sort(), ["1", "2", "3", "4"]);
});

test("validateQuestionSet supports >100 questions and flexible JSON schemas", () => {
  const largePaper = Array.from({ length: 150 }, (_, idx) => ({
    question: `Sample PYQ #${idx + 1}`,
    optionA: `A${idx}`,
    optionB: `B${idx}`,
    optionC: `C${idx}`,
    optionD: `D${idx}`,
    answer: "C"
  }));
  const largeRes = validateQuestionSet(largePaper, { defaultTitle: "Full 150 PYQs" });
  assert.equal(largeRes.ok, true);
  assert.equal(largeRes.questions.length, 150);
  assert.equal(largeRes.questions[0].correctIndex, 2);

  const objectOptionsRes = validateQuestionSet({
    title: "Shift 4",
    section: "Quant",
    questions: [
      {
        q: "x + 1 = 3",
        options: { A: "1", B: "2", C: "3", D: "4" },
        correctOption: "Option B"
      }
    ]
  });
  assert.equal(objectOptionsRes.ok, true);
  assert.equal(objectOptionsRes.title, "Shift 4");
  assert.equal(objectOptionsRes.questions[0].correctIndex, 1);

  assert.equal(validateQuestionSet("{bad json").ok, false);
  assert.equal(validateQuestionSet("[]").ok, false);
});

test("parseQuestionFile handles multi-paper JSON, CSV, and plain-text (.txt) PYQ papers", () => {
  const multiPaperJson = JSON.stringify({
    papers: [
      {
        title: "CHSL 2024 Shift 1",
        questions: [{ prompt: "2 + 2 = ?", options: ["1", "2", "3", "4"], correctIndex: 3 }]
      },
      {
        title: "CHSL 2024 Shift 2",
        questions: [{ prompt: "3 + 3 = ?", options: ["4", "5", "6", "7"], correctIndex: 2 }]
      }
    ]
  });
  const multiRes = parseQuestionFile(multiPaperJson, { filename: "all-shifts.json" });
  assert.equal(multiRes.ok, true);
  assert.equal(multiRes.sets.length, 2);
  assert.equal(multiRes.sets[1].title, "CHSL 2024 Shift 2");

  const csvPayload =
    '\uFEFFid,topic,prompt,optionA,optionB,optionC,optionD,correctIndex\r\n' +
    'c1,Algebra,"If x + 1/x = 5, find x^2 + 1/x^2",21,23,25,27,B\r\n' +
    'c2,Series,"Next term: 2, 4, 8, ?",12,14,16,18,2\r\n';
  const parsedCsv = parseQuestionFile(csvPayload, { filename: "my-quant-drill.csv" });
  assert.equal(parsedCsv.ok, true);
  assert.equal(parsedCsv.questions[0].correctIndex, 1);
  assert.equal(parsedCsv.questions[1].correctIndex, 2);

  const txtPaper = [
    "Section: Quant",
    "Topic: Percentage",
    "1. If 20% of a number is 45, what is 40% of the same number?",
    "A) 60",
    "B) 75",
    "C) 90",
    "D) 105",
    "Answer: C",
    "",
    "Section: Reasoning",
    "Topic: Number Series",
    "Q2. Find the next number: 3, 6, 11, 18, 27, ?",
    "(A) 36  (B) 38  (C) 40  (D) 42",
    "Ans: B"
  ].join("\n");
  const parsedTxt = parseQuestionFile(txtPaper, { filename: "chsl-2023-shift1.txt" });
  assert.equal(parsedTxt.ok, true);
  assert.equal(parsedTxt.title, "chsl-2023-shift1");
  assert.equal(parsedTxt.questions.length, 2);
  assert.equal(parsedTxt.questions[0].section, "Quant");
  assert.equal(parsedTxt.questions[0].correctIndex, 2);
  assert.equal(parsedTxt.questions[1].section, "Reasoning");
  assert.equal(parsedTxt.questions[1].correctIndex, 1);

  assert.equal(parseTxtQuestionPaper("No questions here").ok, false);
});

test("generator filters PYQs, mixes across papers, and generates valid offline variants", () => {
  const paperA = {
    id: "p1",
    label: "Shift 1",
    questions: [
      {
        id: "p1-1",
        section: "Quant",
        topic: "Percentage",
        prompt: "If 20% of a number is 40, find 50% of it.",
        options: ["80", "100", "120", "140"],
        correctIndex: 1
      },
      {
        id: "p1-2",
        section: "General Awareness",
        topic: "Polity",
        prompt: "Which article deals with equality before law?",
        options: ["Article 14", "Article 19", "Article 21", "Article 32"],
        correctIndex: 0
      }
    ]
  };
  const paperB = {
    id: "p2",
    label: "Shift 2",
    questions: [
      {
        id: "p2-1",
        section: "Reasoning",
        topic: "Number Series",
        prompt: "Find the next number in the series: 2, 5, 10, 17, 26, ?",
        options: ["35", "37", "39", "41"],
        correctIndex: 1
      },
      // Duplicate prompt across papers should be deduplicated
      {
        id: "p2-2",
        section: "Quant",
        topic: "Percentage",
        prompt: "If 20% of a number is 40, find 50% of it.",
        options: ["80", "100", "120", "140"],
        correctIndex: 1
      }
    ]
  };

  assert.deepEqual(getAvailableSections([paperA, paperB]), ["General Awareness", "Quant", "Reasoning"]);
  assert.deepEqual(getAvailableTopics([paperA, paperB], "Quant"), ["Percentage"]);

  const filtered = collectFilteredQuestions([paperA, paperB], { sectionFilter: "ALL", topicFilter: "ALL" });
  assert.equal(filtered.length, 3);

  const mixed = buildOfflineMixedSet({ sourceSets: [paperA, paperB], count: 2 });
  assert.equal(mixed.ok, true);
  assert.equal(mixed.questions.length, 2);

  const variants = buildOfflineVariantSet({
    sourceSets: [paperA, paperB],
    sectionFilter: "Quant",
    count: 6
  });
  assert.equal(variants.ok, true);
  assert.equal(variants.questions.length, 6);
  assert.equal(variants.variantCount, 6);
  for (const q of variants.questions) {
    assert.equal(q.options.length, 4);
    assert.equal(new Set(q.options).size, 4);
    assert.ok(q.correctIndex >= 0 && q.correctIndex <= 3);
  }
});

test("generateQuestionsWithGemini validates API key and parses mocked Gemini response", async () => {
  const sourceSets = [
    {
      id: "p1",
      label: "Paper 1",
      questions: [
        {
          id: "q1",
          section: "Quant",
          topic: "Percentage",
          prompt: "If 10% of x is 25, find x.",
          options: ["200", "250", "300", "350"],
          correctIndex: 1
        }
      ]
    }
  ];

  const missingKey = await generateQuestionsWithGemini({ apiKey: "", sourceSets, count: 1 });
  assert.equal(missingKey.ok, false);

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      candidates: [
        {
          content: {
            parts: [
              {
                text: JSON.stringify([
                  {
                    section: "Quant",
                    topic: "Percentage",
                    prompt: "If 25% of a number is 60, find 50% of the number.",
                    options: ["100", "110", "120", "130"],
                    correctIndex: 2
                  }
                ])
              }
            ]
          }
        }
      ]
    })
  });

  try {
    const res = await generateQuestionsWithGemini({
      apiKey: "test-key",
      sourceSets,
      count: 1,
      title: "AI PYQ Drill"
    });
    assert.equal(res.ok, true);
    assert.equal(res.questions.length, 1);
    assert.equal(res.questions[0].correctIndex, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
