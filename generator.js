/**
 * Question generation on top of imported & built-in Previous Year Questions (PYQs).
 * Supports:
 *  1) Offline PYQ Mixer (filter by papers, section, topic and sample randomized drills)
 *  2) Offline Verified Variant Generator (synthesizes new Quant & Reasoning questions modeled on PYQ topics)
 *  3) Optional Gemini API Generator (synthesizes brand-new questions across all subjects via user's API key)
 */

import { shuffleQuestions, validateQuestionSet } from "./engine.js";

function randInt(rng, min, max) {
  return Math.floor(rng() * (max - min + 1)) + min;
}

function pick(rng, arr) {
  return arr[Math.floor(rng() * arr.length)];
}

function formatNum(value) {
  if (Number.isInteger(value)) return String(value);
  const rounded = Number(value.toFixed(2));
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

/**
 * Builds 4 unique options with randomized placement of the correct answer.
 */
function buildMcqOptions(rng, correctStr, candidateDistractors, fallbackFn) {
  const seen = new Set([correctStr]);
  const distractors = [];

  for (const cand of candidateDistractors) {
    const text = String(cand);
    if (!seen.has(text)) {
      seen.add(text);
      distractors.push(text);
      if (distractors.length === 3) break;
    }
  }

  let guard = 0;
  while (distractors.length < 3 && guard < 40) {
    guard += 1;
    const text = String(fallbackFn(guard));
    if (!seen.has(text)) {
      seen.add(text);
      distractors.push(text);
    }
  }

  const all = [correctStr, ...distractors];
  const indexed = all.map((opt, idx) => ({ opt, isCorrect: idx === 0 }));
  const shuffled = shuffleQuestions(indexed, rng);
  return {
    options: shuffled.map((x) => x.opt),
    correctIndex: shuffled.findIndex((x) => x.isCorrect)
  };
}

function buildNumericMcq(rng, correctNum, offsets, { suffix = "", prefix = "", minVal = 1 } = {}) {
  const fmt = (n) => `${prefix}${formatNum(n)}${suffix}`;
  const correctStr = fmt(correctNum);
  const candidates = offsets
    .map((off) => Number((correctNum + off).toFixed(2)))
    .filter((v) => v >= minVal)
    .map(fmt);

  return buildMcqOptions(rng, correctStr, candidates, (step) => {
    const val = Math.max(minVal, Number((correctNum + step * (step % 2 === 0 ? 3 : -2)).toFixed(2)));
    return fmt(val);
  });
}

// ---------------- Verified Parametric Topic Generators ----------------

function genPercentage(rng, section) {
  const variant = randInt(rng, 0, 2);
  if (variant === 0) {
    const p1 = pick(rng, [10, 15, 20, 25, 30, 40]);
    const p2 = pick(rng, [25, 35, 45, 50, 60, 75]);
    const base = randInt(rng, 4, 25) * 20;
    const val1 = (p1 * base) / 100;
    const ans = (p2 * base) / 100;
    const mcq = buildNumericMcq(rng, ans, [-20, -10, 10, 15, 25, 30]);
    return {
      section,
      topic: "Percentage · Variant",
      prompt: `If ${p1}% of a number is ${formatNum(val1)}, what is ${p2}% of the same number?`,
      ...mcq
    };
  }
  if (variant === 1) {
    const inc = pick(rng, [20, 25, 30, 40, 50]);
    const expInc = pick(rng, [5, 8, 10, 12, 16]);
    const reduction = Number((((inc - expInc) / (100 + inc)) * 100).toFixed(2));
    const mcq = buildNumericMcq(rng, reduction, [-4, -2, 2, 4, 5], { suffix: "%" });
    return {
      section,
      topic: "Percentage · Variant",
      prompt: `If the price of a commodity increases by ${inc}%, by what percentage should a household reduce its consumption so that total expenditure increases by only ${expInc}%?`,
      ...mcq
    };
  }
  const a = pick(rng, [10, 15, 20, 25, 30]);
  const b = pick(rng, [10, 12, 20, 25]);
  const net = Number((a - b - (a * b) / 100).toFixed(2));
  const mcq = buildNumericMcq(rng, Math.abs(net), [-3, -1.5, 2, 3.5, 5], {
    suffix: net >= 0 ? "% increase" : "% decrease",
    minVal: 0.5
  });
  return {
    section,
    topic: "Percentage · Variant",
    prompt: `A number is first increased by ${a}% and then decreased by ${b}%. What is the net percentage change in the number?`,
    ...mcq
  };
}

function genProfitLoss(rng, section) {
  const variant = randInt(rng, 0, 1);
  if (variant === 0) {
    const d1 = pick(rng, [10, 15, 20, 25, 30]);
    const d2 = pick(rng, [5, 10, 15, 20]);
    const single = Number((d1 + d2 - (d1 * d2) / 100).toFixed(2));
    const mcq = buildNumericMcq(rng, single, [-4, -2, 2, 3.5, 5], { suffix: "%" });
    return {
      section,
      topic: "Profit, Loss & Discount · Variant",
      prompt: `Find the single equivalent discount for two successive discounts of ${d1}% and ${d2}%.`,
      ...mcq
    };
  }
  const cp = randInt(rng, 5, 20) * 100;
  const gainPct = pick(rng, [10, 12, 15, 20, 25]);
  const sp = Math.round(cp * (1 + gainPct / 100));
  const targetGain = pick(rng, [30, 35, 40].filter((x) => x !== gainPct));
  const targetSp = Math.round(cp * (1 + targetGain / 100));
  const mcq = buildNumericMcq(rng, targetSp, [-150, -80, 60, 120, 200], { prefix: "₹" });
  return {
    section,
    topic: "Profit, Loss & Discount · Variant",
    prompt: `By selling an article for ₹${sp}, a trader gains ${gainPct}%. At what price should it be sold to gain ${targetGain}%?`,
    ...mcq
  };
}

function genRatio(rng, section) {
  const a = randInt(rng, 2, 7);
  const b = randInt(rng, 3, 9);
  const c = randInt(rng, 2, 8);
  const k = randInt(rng, 10, 40);
  const total = (a + b + c) * k;
  const shareB = b * k;
  const mcq = buildNumericMcq(rng, shareB, [-k, k, 2 * k, -2 * k, 30], { prefix: "₹" });
  return {
    section,
    topic: "Ratio & Proportion · Variant",
    prompt: `A sum of ₹${total} is divided among A, B, and C in the ratio ${a} : ${b} : ${c}. What is B's share?`,
    ...mcq
  };
}

function genInterest(rng, section) {
  const rate = pick(rng, [5, 10, 12, 15, 20]);
  const principal = randInt(rng, 2, 12) * 1000;
  const diff = (principal * rate * rate) / 10000;
  const mcq = buildNumericMcq(rng, diff, [-40, -20, 20, 35, 50], { prefix: "₹" });
  return {
    section,
    topic: "Simple & Compound Interest · Variant",
    prompt: `Find the difference between Compound Interest and Simple Interest on ₹${principal} at ${rate}% per annum for 2 years (compounded annually).`,
    ...mcq
  };
}

function genTimeWork(rng, section) {
  const pairs = [
    [10, 15, 6],
    [12, 24, 8],
    [15, 30, 10],
    [20, 30, 12],
    [12, 36, 9],
    [18, 36, 12],
    [24, 40, 15],
    [15, 60, 12]
  ];
  const [d1, d2, together] = pick(rng, pairs);
  const mcq = buildNumericMcq(rng, together, [-3, -2, 2, 3, 4], { suffix: " days" });
  return {
    section,
    topic: "Time & Work · Variant",
    prompt: `A can complete a piece of work in ${d1} days and B can complete the same work in ${d2} days. Working together, in how many days will they finish the work?`,
    ...mcq
  };
}

function genSpeedDistance(rng, section) {
  const pairs = [
    [30, 60, 40],
    [20, 30, 24],
    [40, 60, 48],
    [30, 70, 42],
    [45, 90, 60],
    [24, 40, 30]
  ];
  const [u, v, avg] = pick(rng, pairs);
  const mcq = buildNumericMcq(rng, avg, [-5, -3, 2, 4, 6], { suffix: " km/h" });
  return {
    section,
    topic: "Time, Speed & Distance · Variant",
    prompt: `A car travels from City P to City Q at ${u} km/h and returns along the same route at ${v} km/h. Find the average speed for the entire journey.`,
    ...mcq
  };
}

function genAverage(rng, section) {
  const n = randInt(rng, 5, 11);
  const avg1 = randInt(rng, 18, 45);
  const inc = randInt(rng, 2, 5);
  const newNum = avg1 + (n + 1) * inc;
  const mcq = buildNumericMcq(rng, newNum, [-6, -3, 3, 5, 8]);
  return {
    section,
    topic: "Average · Variant",
    prompt: `The average of ${n} numbers is ${avg1}. When one new number is included, the average increases by ${inc}. Find the new number.`,
    ...mcq
  };
}

function genAlgebra(rng, section) {
  const variant = randInt(rng, 0, 1);
  const k = randInt(rng, 3, 12);
  if (variant === 0) {
    const ans = k * k - 2;
    const mcq = buildNumericMcq(rng, ans, [-4, -2, 2, 4, 6]);
    return {
      section,
      topic: "Algebra · Variant",
      prompt: `If x + 1/x = ${k}, what is the value of x² + 1/x²?`,
      ...mcq
    };
  }
  const ans = k * k * k - 3 * k;
  const mcq = buildNumericMcq(rng, ans, [-12, -6, 6, 9, 15]);
  return {
    section,
    topic: "Algebra · Variant",
    prompt: `If x + 1/x = ${k}, find the value of x³ + 1/x³.`,
    ...mcq
  };
}

function genNumberSystem(rng, section) {
  const variant = randInt(rng, 0, 1);
  if (variant === 0) {
    const hcf = randInt(rng, 4, 18);
    const f1 = pick(rng, [3, 5, 7]);
    const f2 = pick(rng, [2, 4, 8]);
    const a = hcf * f1;
    const b = hcf * f2;
    const lcm = hcf * f1 * f2;
    const mcq = buildNumericMcq(rng, b, [-hcf, hcf, 2 * hcf, -6, 12]);
    return {
      section,
      topic: "HCF & LCM · Variant",
      prompt: `The HCF and LCM of two numbers are ${hcf} and ${lcm} respectively. If one of the numbers is ${a}, find the other number.`,
      ...mcq
    };
  }
  const c = randInt(rng, 2, 7);
  const b = c * randInt(rng, 3, 9);
  const a = randInt(rng, 18, 65);
  const d = randInt(rng, 3, 9);
  const e = randInt(rng, 4, 19);
  const ans = a + Math.floor(b / c) * d - e;
  const mcq = buildNumericMcq(rng, ans, [-6, -3, 3, 5, 9]);
  return {
    section,
    topic: "Simplification · Variant",
    prompt: `Evaluate: ${a} + ${b} ÷ ${c} × ${d} − ${e}`,
    ...mcq
  };
}

function genMensuration(rng, section) {
  const l = randInt(rng, 12, 28);
  const b = randInt(rng, 6, l - 2);
  const perimeter = 2 * (l + b);
  const area = l * b;
  const mcq = buildNumericMcq(rng, area, [-24, -12, 12, 18, 30], { suffix: " cm²" });
  return {
    section,
    topic: "Mensuration · Variant",
    prompt: `The perimeter of a rectangle is ${perimeter} cm and its length is ${l} cm. Find the area of the rectangle.`,
    ...mcq
  };
}

function genNumberSeries(rng, section) {
  const pattern = randInt(rng, 0, 2);
  let seq = [];
  if (pattern === 0) {
    // Increasing step: +d, +(d+step), +(d+2*step)...
    let curr = randInt(rng, 3, 18);
    const startDiff = randInt(rng, 3, 9);
    const step = randInt(rng, 2, 5);
    for (let i = 0; i < 6; i += 1) {
      seq.push(curr);
      curr += startDiff + i * step;
    }
  } else if (pattern === 1) {
    // Square differences: +1, +4, +9, +16, +25
    let curr = randInt(rng, 2, 20);
    for (let i = 1; i <= 6; i += 1) {
      seq.push(curr);
      curr += i * i;
    }
  } else {
    // ×2 ± k
    let curr = randInt(rng, 2, 7);
    const k = pick(rng, [-1, 1, 2, 3]);
    for (let i = 0; i < 6; i += 1) {
      seq.push(curr);
      curr = curr * 2 + k;
    }
  }
  const ans = seq[5];
  const shown = seq.slice(0, 5).join(", ");
  const mcq = buildNumericMcq(rng, ans, [-6, -3, 2, 4, 8]);
  return {
    section,
    topic: "Number Series · Variant",
    prompt: `Find the next number in the series: ${shown}, ?`,
    ...mcq
  };
}

function genCodingReasoning(rng, section) {
  const words = [
    ["TRAIN", "MOUSE"],
    ["PLANT", "WATER"],
    ["LIGHT", "SCORE"],
    ["BRAIN", "CLOCK"],
    ["STONE", "PRIDE"]
  ];
  const [w1, w2] = pick(rng, words);
  const shift = randInt(rng, 2, 5);
  const encode = (word, s) =>
    word
      .split("")
      .map((ch) => String.fromCharCode(((ch.charCodeAt(0) - 65 + s) % 26) + 65))
      .join("");

  const exEncoded = encode(w1, shift);
  const ans = encode(w2, shift);
  const d1 = encode(w2, shift + 1);
  const d2 = encode(w2, shift - 1);
  const d3 = ans.slice(0, -1) + String.fromCharCode(((ans.charCodeAt(ans.length - 1) - 65 + 2) % 26) + 65);

  const mcq = buildMcqOptions(rng, ans, [d1, d2, d3], (step) => encode(w2, shift + step + 1));
  return {
    section,
    topic: "Coding-Decoding · Variant",
    prompt: `In a certain code language, '${w1}' is written as '${exEncoded}'. How will '${w2}' be written in that same code language?`,
    ...mcq
  };
}

const TOPIC_GENERATOR_RULES = [
  { test: /percent/i, fn: genPercentage, defaultSection: "Quant" },
  { test: /profit|loss|discount|marked/i, fn: genProfitLoss, defaultSection: "Quant" },
  { test: /ratio|proportion|age|mixture|partner/i, fn: genRatio, defaultSection: "Quant" },
  { test: /interest|compound|simple/i, fn: genInterest, defaultSection: "Quant" },
  { test: /work|pipe|cistern/i, fn: genTimeWork, defaultSection: "Quant" },
  { test: /speed|distance|train|boat/i, fn: genSpeedDistance, defaultSection: "Quant" },
  { test: /average/i, fn: genAverage, defaultSection: "Quant" },
  { test: /algebra|x\s*\+\s*1\/x/i, fn: genAlgebra, defaultSection: "Quant" },
  { test: /number\s*system|hcf|lcm|simplif|divisib|bodmas/i, fn: genNumberSystem, defaultSection: "Quant" },
  { test: /mensuration|geometry|perimeter|area|volume|triangle|circle|rectangle/i, fn: genMensuration, defaultSection: "Quant" },
  { test: /series|missing\s*number/i, fn: genNumberSeries, defaultSection: "Reasoning" },
  { test: /coding|decoding|analogy|letter/i, fn: genCodingReasoning, defaultSection: "Reasoning" }
];

function matchGeneratorForPyq(pyq) {
  const haystack = `${pyq.topic || ""} ${pyq.prompt || ""}`;
  for (const rule of TOPIC_GENERATOR_RULES) {
    if (rule.test.test(haystack)) {
      return rule;
    }
  }
  if (/quant|math|arithmetic/i.test(pyq.section || "")) {
    return { fn: genPercentage, defaultSection: "Quant" };
  }
  if (/reason/i.test(pyq.section || "")) {
    return { fn: genNumberSeries, defaultSection: "Reasoning" };
  }
  return null;
}

/**
 * Returns sorted unique section names across source sets.
 */
export function getAvailableSections(sourceSets) {
  const sections = new Set();
  for (const setObj of sourceSets || []) {
    for (const q of setObj.questions || []) {
      if (q.section) sections.add(q.section);
    }
  }
  return Array.from(sections).sort();
}

/**
 * Returns sorted unique topic names across source sets (optionally filtered by section).
 */
export function getAvailableTopics(sourceSets, sectionFilter = "ALL") {
  const topics = new Set();
  for (const setObj of sourceSets || []) {
    for (const q of setObj.questions || []) {
      if (sectionFilter !== "ALL" && q.section !== sectionFilter) continue;
      if (q.topic) topics.add(q.topic);
    }
  }
  return Array.from(topics).sort();
}

/**
 * Collects deduplicated PYQs matching section & topic filters across selected sets,
 * keeping a balanced order across papers.
 */
export function collectFilteredQuestions(
  sourceSets,
  { sectionFilter = "ALL", topicFilter = "ALL" } = {}
) {
  const buckets = (sourceSets || []).map((setObj) =>
    (setObj.questions || []).filter((q) => {
      if (sectionFilter !== "ALL" && q.section !== sectionFilter) return false;
      if (topicFilter !== "ALL" && q.topic !== topicFilter) return false;
      return true;
    })
  );

  const seenPrompts = new Set();
  const interleaved = [];
  let round = 0;
  let added = true;

  while (added) {
    added = false;
    for (const bucket of buckets) {
      if (round < bucket.length) {
        added = true;
        const q = bucket[round];
        const key = q.prompt.trim().toLowerCase();
        if (!seenPrompts.has(key)) {
          seenPrompts.add(key);
          interleaved.push(q);
        }
      }
    }
    round += 1;
  }

  return interleaved;
}

function shuffleQuestionOptions(q, rng) {
  const tagged = q.options.map((text, idx) => ({ text, isCorrect: idx === q.correctIndex }));
  const shuffled = shuffleQuestions(tagged, rng);
  return {
    ...q,
    options: shuffled.map((x) => x.text),
    correctIndex: shuffled.findIndex((x) => x.isCorrect)
  };
}

/**
 * Generates a randomized practice drill directly from the filtered PYQ pool.
 */
export function buildOfflineMixedSet({
  sourceSets,
  sectionFilter = "ALL",
  topicFilter = "ALL",
  count = 25,
  rng = Math.random
}) {
  const pool = collectFilteredQuestions(sourceSets, { sectionFilter, topicFilter });
  if (pool.length === 0) {
    return { ok: false, error: "No questions match the selected papers, section, and topic." };
  }

  const targetCount = Math.min(Math.max(1, count), pool.length);
  const picked = shuffleQuestions(pool, rng).slice(0, targetCount);
  const questions = picked.map((q, idx) => ({
    ...shuffleQuestionOptions(q, rng),
    id: `mix-q${idx + 1}`
  }));

  return {
    ok: true,
    questions,
    summary: `Mixed ${questions.length} PYQs from ${pool.length} matching questions.`
  };
}

/**
 * Generates new parametric Quant & Reasoning questions modeled after the selected PYQs.
 * Non-parametric factual/verbal PYQs (e.g., English/GA) are included with shuffled options
 * if the selected pool contains only factual/verbal items.
 */
export function buildOfflineVariantSet({
  sourceSets,
  sectionFilter = "ALL",
  topicFilter = "ALL",
  count = 25,
  rng = Math.random
}) {
  const pool = collectFilteredQuestions(sourceSets, { sectionFilter, topicFilter });
  if (pool.length === 0) {
    return { ok: false, error: "No questions match the selected papers, section, and topic." };
  }

  const targetCount = Math.max(1, Math.min(200, count));
  const shuffledPool = shuffleQuestions(pool, rng);
  const seenPrompts = new Set();
  const generated = [];
  let variantCount = 0;
  let pyqCount = 0;

  let cursor = 0;
  let attempts = 0;
  const maxAttempts = targetCount * 10;

  while (generated.length < targetCount && attempts < maxAttempts) {
    attempts += 1;
    const base = shuffledPool[cursor % shuffledPool.length];
    cursor += 1;

    const rule = matchGeneratorForPyq(base);
    if (rule) {
      const candidate = rule.fn(rng, base.section || rule.defaultSection);
      const key = candidate.prompt.trim().toLowerCase();
      if (!seenPrompts.has(key)) {
        seenPrompts.add(key);
        generated.push({
          id: `var-q${generated.length + 1}`,
          ...candidate
        });
        variantCount += 1;
      }
      continue;
    }

    // Factual/verbal PYQ fallback: include option-shuffled PYQ if not already added
    const baseKey = base.prompt.trim().toLowerCase();
    if (!seenPrompts.has(baseKey)) {
      seenPrompts.add(baseKey);
      generated.push({
        ...shuffleQuestionOptions(base, rng),
        id: `var-q${generated.length + 1}`
      });
      pyqCount += 1;
    }
  }

  // If factual-only pool had fewer unique PYQs than targetCount, top up with math/reasoning variants
  while (generated.length < targetCount && attempts < maxAttempts + 100) {
    attempts += 1;
    const fallbackFn = pick(rng, TOPIC_GENERATOR_RULES).fn;
    const candidate = fallbackFn(rng, sectionFilter !== "ALL" ? sectionFilter : "Quant");
    const key = candidate.prompt.trim().toLowerCase();
    if (!seenPrompts.has(key)) {
      seenPrompts.add(key);
      generated.push({
        id: `var-q${generated.length + 1}`,
        ...candidate
      });
      variantCount += 1;
    }
  }

  const summaryParts = [];
  if (variantCount > 0) summaryParts.push(`${variantCount} newly generated variants`);
  if (pyqCount > 0) summaryParts.push(`${pyqCount} option-shuffled factual/verbal PYQs`);

  return {
    ok: true,
    questions: generated,
    variantCount,
    pyqCount,
    summary: `Generated ${summaryParts.join(" + ")} based on your selected PYQs.`
  };
}

/**
 * Generates brand-new SSC CHSL questions using the user's Gemini API key,
 * conditioned on representative sample questions from their imported PYQs.
 */
export async function generateQuestionsWithGemini({
  apiKey,
  model = "gemini-2.5-flash",
  sourceSets,
  sectionFilter = "ALL",
  topicFilter = "ALL",
  count = 10,
  title = "AI Generated PYQ Set"
}) {
  const cleanKey = String(apiKey || "").trim();
  if (!cleanKey) {
    return { ok: false, error: "Enter your Gemini API key first." };
  }

  const pool = collectFilteredQuestions(sourceSets, { sectionFilter, topicFilter });
  if (pool.length === 0) {
    return { ok: false, error: "No source PYQs match your selected papers and filters." };
  }

  const targetCount = Math.max(1, Math.min(50, count));
  const examples = shuffleQuestions(pool).slice(0, 12).map((q) => ({
    section: q.section,
    topic: q.topic,
    prompt: q.prompt,
    options: q.options,
    correctIndex: q.correctIndex
  }));

  const instruction = [
    `Generate exactly ${targetCount} NEW, original SSC CHSL Tier 1 multiple-choice questions inspired by the style, difficulty, and topics of the following previous-year questions.`,
    sectionFilter !== "ALL" ? `Target section: ${sectionFilter}.` : "",
    topicFilter !== "ALL" ? `Target topic: ${topicFilter}.` : "",
    `Rules:`,
    `1. Do NOT copy the example questions verbatim; create fresh questions with accurate, verified answers.`,
    `2. Each item must have: "section", "topic", "prompt", "options" (array of exactly 4 distinct strings), and "correctIndex" (integer 0, 1, 2, or 3).`,
    `3. Return ONLY a valid JSON array of ${targetCount} objects.`,
    `Reference PYQs:\n${JSON.stringify(examples)}`
  ]
    .filter(Boolean)
    .join("\n\n");

  const cleanModel = String(model || "gemini-2.5-flash").trim();
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(cleanModel)}:generateContent?key=${encodeURIComponent(cleanKey)}`;

  let response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: instruction }] }],
        generationConfig: {
          responseMimeType: "application/json",
          temperature: 0.7
        }
      })
    });
  } catch (err) {
    return { ok: false, error: `Network error calling Gemini API: ${err.message}` };
  }

  let data;
  try {
    data = await response.json();
  } catch {
    return { ok: false, error: `Gemini API returned invalid JSON (HTTP ${response.status}).` };
  }

  if (!response.ok) {
    const apiMsg = data?.error?.message || `HTTP ${response.status}`;
    return { ok: false, error: `Gemini API error: ${apiMsg}` };
  }

  const rawText = data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
  const cleanedJson = rawText
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```\s*$/i, "")
    .trim();

  const validation = validateQuestionSet(cleanedJson, {
    defaultTitle: title,
    defaultSection: sectionFilter !== "ALL" ? sectionFilter : "Custom"
  });

  if (!validation.ok) {
    return { ok: false, error: `Generated output failed validation: ${validation.error}` };
  }

  return {
    ok: true,
    title: validation.title,
    section: validation.section,
    questions: validation.questions,
    summary: `AI generated ${validation.questions.length} new questions from ${examples.length} reference PYQs.`
  };
}
