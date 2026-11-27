/**
 * Pure domain logic for SSC CHSL 35s Practice Trainer.
 * Handles scoring (+2 / -0.50), 35s per-question countdown/auto-skip navigation,
 * result classification, question shuffling, and unlimited multi-format PYQ parsing (.json, .csv, .txt).
 */

export const QUESTION_TIME_LIMIT_SEC = 35;
export const QUESTION_TIME_LIMIT_MS = QUESTION_TIME_LIMIT_SEC * 1000;
export const MARKS_RIGHT = 2.0;
export const MARKS_WRONG = 0.5;

/**
 * Formats per-question remaining milliseconds as whole seconds (e.g., "35s").
 */
export function formatQuestionSeconds(remainingMs) {
  const totalSeconds = Math.ceil(Math.max(0, remainingMs) / 1000);
  return `${totalSeconds}s`;
}

/**
 * Computes remaining cumulative time budget (in ms) for a single question.
 */
export function getQuestionRemainingMs({
  totalMs = 0,
  activeEnteredAt = null,
  now = 0,
  limitMs = QUESTION_TIME_LIMIT_MS
}) {
  const baseSpent = Math.max(0, totalMs || 0);
  const liveSpent = activeEnteredAt !== null ? Math.max(0, now - activeEnteredAt) : 0;
  return Math.max(0, limitMs - (baseSpent + liveSpent));
}

/**
 * Finds the next non-expired question index in forward circular order for manual Skip / Save & Next.
 */
export function findNextAvailableIndex({ currentIndex, totalQuestions, expired = [] }) {
  if (totalQuestions <= 1) return null;
  for (let offset = 1; offset < totalQuestions; offset += 1) {
    const candidate = (currentIndex + offset) % totalQuestions;
    if (!expired[candidate]) {
      return candidate;
    }
  }
  return null;
}

/**
 * Decides the next navigation action when the current question's 35s limit expires.
 * Submits when the last question finishes (unless unvisited questions remain from out-of-order jumps).
 */
export function resolveTimeoutTransition({
  currentIndex,
  totalQuestions,
  expired = [],
  visited = [],
  answers = []
}) {
  if (totalQuestions <= 0) {
    return { action: "finish" };
  }

  for (let j = currentIndex + 1; j < totalQuestions; j += 1) {
    if (!expired[j] && (!visited[j] || answers[j] === null)) {
      return { action: "next", nextIndex: j };
    }
  }

  if (currentIndex === totalQuestions - 1) {
    for (let j = 0; j < totalQuestions - 1; j += 1) {
      if (!expired[j] && !visited[j]) {
        return { action: "next", nextIndex: j };
      }
    }
    return { action: "finish" };
  }

  for (let j = 0; j < currentIndex; j += 1) {
    if (!expired[j] && !visited[j]) {
      return { action: "next", nextIndex: j };
    }
  }

  for (let j = 0; j < currentIndex; j += 1) {
    if (!expired[j] && answers[j] === null) {
      return { action: "next", nextIndex: j };
    }
  }

  return { action: "finish" };
}

/**
 * Analyzes a completed run into headline score, accuracy, and correct/wrong/unattempted groups.
 */
export function analyzeRun({ questions, answers }) {
  const items = questions.map((question, index) => {
    const selectedIndex = answers[index] ?? null;
    const isAttempted = selectedIndex !== null;
    const isCorrect = isAttempted && selectedIndex === question.correctIndex;
    const isWrong = isAttempted && selectedIndex !== question.correctIndex;

    let status = "unattempted";
    if (isCorrect) status = "correct";
    else if (isWrong) status = "wrong";

    return {
      index,
      number: index + 1,
      question,
      selectedIndex,
      isAttempted,
      isCorrect,
      isWrong,
      status
    };
  });

  const groups = {
    correct: items.filter((item) => item.status === "correct"),
    wrong: items.filter((item) => item.status === "wrong"),
    unattempted: items.filter((item) => item.status === "unattempted")
  };

  const correctCount = groups.correct.length;
  const wrongCount = groups.wrong.length;
  const attemptedCount = correctCount + wrongCount;
  const unattemptedCount = groups.unattempted.length;

  const netScore = Number((correctCount * MARKS_RIGHT - wrongCount * MARKS_WRONG).toFixed(2));
  const maxScore = questions.length * MARKS_RIGHT;
  const accuracyPct = attemptedCount > 0 ? Number(((correctCount / attemptedCount) * 100).toFixed(1)) : 0;

  const missedItems = items.filter((item) => item.isWrong || !item.isAttempted);
  const missedQuestions = missedItems.map((item) => item.question);

  return {
    totalQuestions: questions.length,
    attemptedCount,
    correctCount,
    wrongCount,
    unattemptedCount,
    netScore,
    maxScore,
    accuracyPct,
    missedItems,
    missedQuestions,
    groups,
    items
  };
}

/**
 * Returns a new Fisher-Yates shuffled copy of the questions array.
 */
export function shuffleQuestions(questions, rng = Math.random) {
  const copy = [...questions];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function extractOptionsFromObject(q) {
  if (Array.isArray(q.options)) {
    return q.options;
  }
  if (q.options && typeof q.options === "object") {
    return [
      q.options.A ?? q.options.a ?? q.options[0],
      q.options.B ?? q.options.b ?? q.options[1],
      q.options.C ?? q.options.c ?? q.options[2],
      q.options.D ?? q.options.d ?? q.options[3]
    ];
  }
  const hasNamedOpts =
    q.optionA !== undefined ||
    q.option1 !== undefined ||
    q.a !== undefined ||
    q.A !== undefined ||
    q.optA !== undefined;
  if (hasNamedOpts) {
    return [
      q.optionA ?? q.option1 ?? q.optA ?? q.a ?? q.A,
      q.optionB ?? q.option2 ?? q.optB ?? q.b ?? q.B,
      q.optionC ?? q.option3 ?? q.optC ?? q.c ?? q.C,
      q.optionD ?? q.option4 ?? q.optD ?? q.d ?? q.D
    ];
  }
  return null;
}

function resolveCorrectIndex(q, cleanOptions) {
  if (Number.isInteger(q.correctIndex)) {
    return q.correctIndex;
  }
  const raw =
    q.correctIndex ?? q.correctOption ?? q.correct ?? q.answer ?? q.ans ?? q.key ?? "";
  return parseCorrectOptionValue(raw, cleanOptions);
}

/**
 * Validates and normalizes a single custom PYQ JSON payload (unlimited questions).
 * Accepts flexible keys: prompt/question/q, options array or optionA..D, correctIndex/answer/correct.
 */
export function validateQuestionSet(rawInput, { defaultTitle = "Custom Set", defaultSection = "Custom" } = {}) {
  let parsed = rawInput;
  if (typeof rawInput === "string") {
    const trimmed = rawInput.trim();
    if (!trimmed) {
      return { ok: false, error: "Paste JSON or choose a file first." };
    }
    try {
      parsed = JSON.parse(trimmed);
    } catch (err) {
      return { ok: false, error: `Invalid JSON: ${err.message}` };
    }
  }

  let title = defaultTitle;
  let section = defaultSection;
  let items = parsed;

  if (parsed && !Array.isArray(parsed) && typeof parsed === "object") {
    if (typeof parsed.title === "string" && parsed.title.trim()) title = parsed.title.trim();
    else if (typeof parsed.name === "string" && parsed.name.trim()) title = parsed.name.trim();
    else if (typeof parsed.paper === "string" && parsed.paper.trim()) title = parsed.paper.trim();
    if (typeof parsed.section === "string" && parsed.section.trim()) section = parsed.section.trim();
    items = parsed.questions ?? parsed.items ?? parsed.data;
  }

  if (!Array.isArray(items) || items.length === 0) {
    return {
      ok: false,
      error: "Expected a non-empty JSON array of questions (or { title, questions: [...] })."
    };
  }

  const normalized = [];
  const seenIds = new Set();

  for (let i = 0; i < items.length; i += 1) {
    const q = items[i];
    const num = i + 1;

    if (!q || typeof q !== "object" || Array.isArray(q)) {
      return { ok: false, error: `Question #${num} must be a JSON object.` };
    }

    const rawPrompt = q.prompt ?? q.question ?? q.questionText ?? q.q ?? "";
    if (typeof rawPrompt !== "string" || !rawPrompt.trim()) {
      return { ok: false, error: `Question #${num} is missing a non-empty "prompt" or "question" string.` };
    }

    const rawOptions = extractOptionsFromObject(q);
    if (!Array.isArray(rawOptions) || rawOptions.length !== 4) {
      return { ok: false, error: `Question #${num} must have 4 options ("options" array or optionA..optionD).` };
    }

    const cleanOptions = rawOptions.map((opt) =>
      typeof opt === "string" ? opt.trim() : typeof opt === "number" ? String(opt) : ""
    );
    if (cleanOptions.some((opt) => !opt)) {
      return { ok: false, error: `Question #${num} has an empty or invalid option.` };
    }
    if (new Set(cleanOptions).size !== 4) {
      return { ok: false, error: `Question #${num} has duplicate options.` };
    }

    const resolvedIndex = resolveCorrectIndex(q, cleanOptions);
    if (!Number.isInteger(resolvedIndex) || resolvedIndex < 0 || resolvedIndex > 3) {
      return {
        ok: false,
        error: `Question #${num} must have a valid answer ("correctIndex" 0–3 or "answer" A–D).`
      };
    }

    const rawId =
      typeof q.id === "string" && q.id.trim()
        ? q.id.trim()
        : typeof q.id === "number"
          ? `q-${q.id}`
          : `custom-q${num}`;
    const uniqueId = seenIds.has(rawId) ? `${rawId}-${num}` : rawId;
    seenIds.add(uniqueId);

    const qSection = typeof q.section === "string" && q.section.trim() ? q.section.trim() : section;
    const qTopic = typeof q.topic === "string" && q.topic.trim() ? q.topic.trim() : "General";

    normalized.push({
      id: uniqueId,
      section: qSection,
      topic: qTopic,
      prompt: rawPrompt.trim(),
      options: cleanOptions,
      correctIndex: resolvedIndex
    });
  }

  return {
    ok: true,
    title,
    section: normalized[0].section || section,
    questions: normalized
  };
}

function detectCsvDelimiter(firstLine) {
  const counts = {
    ",": (firstLine.match(/,/g) || []).length,
    "\t": (firstLine.match(/\t/g) || []).length,
    ";": (firstLine.match(/;/g) || []).length
  };
  if (counts["\t"] > counts[","] && counts["\t"] >= counts[";"]) return "\t";
  if (counts[";"] > counts[","] && counts[";"] >= counts["\t"]) return ";";
  return ",";
}

function parseCsvRows(text) {
  const firstLine = text.split(/\r?\n/, 1)[0] || "";
  const delimiter = detectCsvDelimiter(firstLine);
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        cell += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === delimiter) {
      row.push(cell.trim());
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cell.trim());
      if (row.some((v) => v.length > 0)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += ch;
    }
  }

  row.push(cell.trim());
  if (row.some((v) => v.length > 0)) rows.push(row);
  return rows;
}

function parseCorrectOptionValue(raw, options = null) {
  if (typeof raw === "number" && Number.isInteger(raw)) {
    return raw >= 0 && raw <= 3 ? raw : -1;
  }

  const text = String(raw ?? "").trim();
  if (!text) return -1;

  const upper = text.toUpperCase();
  const letters = { A: 0, B: 1, C: 2, D: 3 };
  if (upper in letters) return letters[upper];

  const optionPrefixMatch = upper.match(/^(?:OPTION\s*)?\(?([ABCD])\)?\.?$/);
  if (optionPrefixMatch) {
    return letters[optionPrefixMatch[1]];
  }

  const leadingOptionMatch = upper.match(/^(?:OPTION\s*)?\(?([ABCD])\)?\s*[.):\-]\s*.+$/);
  if (leadingOptionMatch) {
    return letters[leadingOptionMatch[1]];
  }

  const leadingNumOptionMatch = upper.match(/^(?:OPTION\s*)?\(?([1-4])\)?\s*[.):\-]\s*.+$/);
  if (leadingNumOptionMatch) {
    return Number(leadingNumOptionMatch[1]) - 1;
  }

  if (/^[0-3]$/.test(upper)) return Number(upper);
  if (upper === "4") return 3;

  if (Array.isArray(options)) {
    const exactMatch = options.findIndex((opt) => opt.toLowerCase() === text.toLowerCase());
    if (exactMatch !== -1) return exactMatch;
  }

  return -1;
}

function findColumnIndex(headers, candidates) {
  return headers.findIndex((h) => candidates.includes(h));
}

function cleanPdfUiArtifacts(line) {
  return line
    .replace(/[\uE000-\uF8FF✔✓✅✗✘]/g, " ")
    .replace(/\bAdd New Test\b/gi, " ")
    .replace(/\bGenerate HTML Link\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function splitMultiOptionsLine(line, allowNumeric) {
  const letterStart = line.match(/^\s*(?:\(([ABCD])\)|([ABCD])[.):\-])\s*/i);
  if (letterStart) {
    const markerRegex = /(?:^|\s+)(?:\(([ABCD])\)|([ABCD])[.):\-])\s*/gi;
    const matches = [];
    for (const m of line.matchAll(markerRegex)) {
      const key = (m[1] || m[2]).toUpperCase();
      matches.push({ key, index: m.index, end: m.index + m[0].length });
    }
    const order = { A: 0, B: 1, C: 2, D: 3 };
    const validSeq = [];
    for (const item of matches) {
      if (validSeq.length === 0) {
        validSeq.push(item);
      } else if (order[item.key] > order[validSeq[validSeq.length - 1].key]) {
        validSeq.push(item);
      }
    }
    if (validSeq.length >= 2) {
      return {
        isNumeric: false,
        entries: validSeq.map((item, idx) => {
          const nextStart = idx + 1 < validSeq.length ? validSeq[idx + 1].index : line.length;
          return { key: item.key, text: line.slice(item.end, nextStart).trim() };
        })
      };
    }
  }

  const numStart = line.match(/^\s*(?:\(([1-4])\)|([1-4])[.):\-])\s*/);
  if (numStart && (allowNumeric || (numStart[1] || numStart[2]) === "1")) {
    const markerRegex = /(?:^|\s+)(?:\(([1-4])\)|([1-4])[.):\-])\s*/g;
    const matches = [];
    for (const m of line.matchAll(markerRegex)) {
      const num = Number(m[1] || m[2]);
      matches.push({ num, key: ["A", "B", "C", "D"][num - 1], index: m.index, end: m.index + m[0].length });
    }
    const validSeq = [];
    for (const item of matches) {
      if (validSeq.length === 0) {
        validSeq.push(item);
      } else if (item.num > validSeq[validSeq.length - 1].num) {
        validSeq.push(item);
      }
    }
    if (validSeq.length >= 2 && (allowNumeric || validSeq.length === 4 || validSeq[0].num === 1)) {
      return {
        isNumeric: true,
        entries: validSeq.map((item, idx) => {
          const nextStart = idx + 1 < validSeq.length ? validSeq[idx + 1].index : line.length;
          return { key: item.key, text: line.slice(item.end, nextStart).trim() };
        })
      };
    }
  }

  return null;
}

function parseAnswerKeyToken(token, zeroBased) {
  const upper = String(token || "").trim().toUpperCase();
  const letters = { A: 0, B: 1, C: 2, D: 3 };
  if (upper in letters) return letters[upper];
  if (/^[1-4]$/.test(upper) && !zeroBased) return Number(upper) - 1;
  if (/^[0-3]$/.test(upper) && zeroBased) return Number(upper);
  return -1;
}

/**
 * Parses a plain-text (.txt) or PDF-extracted previous-year question paper into a validated set.
 * Supports numbered questions (1., Q1., Q.1, Question 1:), A-D or 1-4 options (1, 2, or 4 per line,
 * hanging option labels, or multi-line options), SSC checkmark (✔/✓) answers, Solution blocks,
 * per-question Answer:/Ans:/Key: lines, trailing Answer Key blocks, and Section:/Topic: metadata.
 */
export function parseTxtQuestionPaper(
  rawText,
  { defaultTitle = "Custom Set", defaultSection = "Custom" } = {}
) {
  const lines = String(rawText || "").replace(/^\uFEFF/, "").split(/\r?\n/);
  const questions = [];
  const answerKeyEntries = [];
  let currentSection = defaultSection;
  let currentTopic = "General";
  let current = null;
  let inAnswerKey = false;

  const flushCurrent = () => {
    if (!current) return;
    const prompt = current.promptLines.join("\n").trim();
    const opts = ["A", "B", "C", "D"].map((k) => current.options[k] || "");
    let rawAns = current.answerRaw;
    if (current.usesNumericOptions && /^[1-4]$/.test(rawAns.trim())) {
      rawAns = String(Number(rawAns.trim()) - 1);
    }
    const ans = parseCorrectOptionValue(rawAns, opts);
    if (prompt || opts.some(Boolean)) {
      questions.push({
        id: `txt-q${questions.length + 1}`,
        section: current.section || currentSection,
        topic: current.topic || currentTopic,
        prompt,
        options: opts,
        correctIndex: ans
      });
    }
    current = null;
  };

  for (const rawLine of lines) {
    const rawTrimmed = rawLine.trim();
    if (!rawTrimmed) {
      if (current && !current.startedOptions && !current.inSolution && current.promptLines.length > 0) {
        current.promptLines.push("");
      }
      continue;
    }

    const hasCheckMark = /[✔✓✅\uf00c\uf058]/.test(rawTrimmed);
    const line = cleanPdfUiArtifacts(rawTrimmed);
    if (!line || /^O\s+V\s+E\s+R\s+V\s+I\s+E\s+W$/i.test(line)) {
      continue;
    }

    if (/^(?:Question\s*ID|Status|Chosen\s*Option|Section\s*Name|Mapping\s*Id)\s*:/i.test(line)) {
      continue;
    }

    const answerKeyHeader = line.match(/^(?:Answer\s*Key|Answers|Key)\s*:?\s*(.*)$/i);
    if (answerKeyHeader && (!current || current.startedOptions)) {
      flushCurrent();
      inAnswerKey = true;
      if (answerKeyHeader[1]) {
        const matches = answerKeyHeader[1].matchAll(/(?:Q\.?\s*)?(\d+)\s*[.):\-–]\s*\(?([A-D0-4])\)?/gi);
        for (const m of matches) {
          answerKeyEntries.push({ qNum: Number(m[1]), token: m[2] });
        }
      }
      continue;
    }

    if (inAnswerKey) {
      const matches = line.matchAll(/(?:Q\.?\s*)?(\d+)\s*[.):\-–]\s*\(?([A-D0-4])\)?/gi);
      let found = false;
      for (const m of matches) {
        found = true;
        answerKeyEntries.push({ qNum: Number(m[1]), token: m[2] });
      }
      if (found) continue;
    }

    const sectionMeta = line.match(/^Section\s*:\s*(.+)$/i);
    if (sectionMeta) {
      const val = sectionMeta[1].trim();
      if (current && !current.startedOptions) current.section = val;
      else currentSection = val;
      continue;
    }

    const topicMeta = line.match(/^Topic\s*:\s*(.+)$/i);
    if (topicMeta) {
      const val = topicMeta[1].trim();
      if (current && !current.startedOptions) current.topic = val;
      else currentTopic = val;
      continue;
    }

    if (current && !current.startedOptions && /^Ans(?:wer)?$/i.test(line)) {
      current.expectingNumericOptions = true;
      continue;
    }

    const optCount = current ? Object.keys(current.options).length : 0;
    const explicitQRegex = /^(?:Question\s*\d+\s*[.):\-]?|Q\.\s*\d+\s*[.):\-]?|Q\s*\d+\s*[.):\-])\s+(.+)$/i;
    const isExplicitQuestion = explicitQRegex.test(line);
    const numStart =
      line.match(explicitQRegex) || line.match(/^(?:\d+)\s*[.):\-]\s+(.+)$/);
    const looksLikeNumericOption =
      current &&
      !current.inSolution &&
      optCount < 4 &&
      /^(?:Ans\s+)?(?:\([1-4]\)|[1-4][.)])\s*/i.test(line) &&
      (current.usesNumericOptions ||
        current.expectingNumericOptions ||
        /^(?:Ans\s+1\.|\(?1\)[.)]?)/i.test(line) ||
        (current.startedOptions && /^[2-4][.)]\s*/.test(line)));

    if (numStart && (isExplicitQuestion || !current || current.inSolution || optCount === 4 || !looksLikeNumericOption)) {
      if (!looksLikeNumericOption || isExplicitQuestion || optCount === 4 || (current && current.inSolution)) {
        flushCurrent();
        inAnswerKey = false;
        current = {
          section: currentSection,
          topic: currentTopic,
          promptLines: [numStart[1].trim()],
          options: {},
          startedOptions: false,
          usesNumericOptions: false,
          expectingNumericOptions: false,
          inSolution: false,
          pendingOptionKey: null,
          lastOptionKey: null,
          answerRaw: ""
        };
        continue;
      }
    }

    if (!current) {
      continue;
    }

    const ansMatch = line.match(/^(?:Correct\s*Answer|Correct\s*Option|Right\s*Answer|Answer|Ans|Key)\s*[.:=\-]\s*(.+)$/i);
    if (ansMatch) {
      current.answerRaw = ansMatch[1].trim();
      current.pendingOptionKey = null;
      continue;
    }

    const solMatch = line.match(/^(?:Sol(?:ution)?|Explanation|Detailed\s*Solution|Key\s*Concept)\s*[.:=\-]\s*(.*)$/i);
    if (solMatch && current.startedOptions) {
      current.inSolution = true;
      current.pendingOptionKey = null;
      if (!current.answerRaw && solMatch[1]) {
        const solAns = solMatch[1].match(/^\(?([ABCD1-4])\)?(?:\s*[.):\-]|$)/i);
        if (solAns) current.answerRaw = solAns[1].toUpperCase();
      }
      continue;
    }

    if (current.inSolution) {
      continue;
    }

    if (current.pendingOptionKey) {
      current.options[current.pendingOptionKey] = line;
      current.lastOptionKey = current.pendingOptionKey;
      if (hasCheckMark) current.answerRaw = current.pendingOptionKey;
      current.pendingOptionKey = null;
      continue;
    }

    const multiOpts = splitMultiOptionsLine(line, current.startedOptions || current.expectingNumericOptions);
    if (multiOpts) {
      current.startedOptions = true;
      current.usesNumericOptions = multiOpts.isNumeric;
      for (const entry of multiOpts.entries) {
        current.options[entry.key] = entry.text;
        current.lastOptionKey = entry.key;
      }
      current.pendingOptionKey = null;
      continue;
    }

    const hangingLetterOpt = line.match(/^\(?([ABCD])\)?\s*[.):\-]?\s*$/i);
    if (hangingLetterOpt && (current.startedOptions || hangingLetterOpt[1].toUpperCase() === "A" || /[.):\-]/.test(line))) {
      current.startedOptions = true;
      current.pendingOptionKey = hangingLetterOpt[1].toUpperCase();
      continue;
    }

    const letterOptMatch = line.match(/^\(?([ABCD])\)?\s*[.):\-]\s*(.+)$/i);
    if (letterOptMatch && !/^[A-Z]\./.test(letterOptMatch[2].trim())) {
      current.startedOptions = true;
      const key = letterOptMatch[1].toUpperCase();
      current.options[key] = letterOptMatch[2].trim();
      current.lastOptionKey = key;
      if (hasCheckMark) {
        current.answerRaw = key;
      }
      continue;
    }

    const numOptMatch = line.match(/^(?:Ans\s+)?(?:\(([1-4])\)|([1-4])[.)])\s*(.+)$/i);
    if (numOptMatch && optCount < 4) {
      current.startedOptions = true;
      current.usesNumericOptions = true;
      const numVal = Number(numOptMatch[1] || numOptMatch[2]);
      const key = ["A", "B", "C", "D"][numVal - 1];
      current.options[key] = numOptMatch[3].trim();
      current.lastOptionKey = key;
      if (hasCheckMark) {
        current.answerRaw = key;
      }
      continue;
    }

    if (!current.startedOptions) {
      current.promptLines.push(line);
    } else if (current.lastOptionKey && !current.answerRaw) {
      current.options[current.lastOptionKey] = `${current.options[current.lastOptionKey]} ${line}`.trim();
    }
  }

  flushCurrent();

  if (answerKeyEntries.length > 0 && questions.length > 0) {
    const hasZero = answerKeyEntries.some((e) => e.token === "0");
    for (const entry of answerKeyEntries) {
      const target = questions[entry.qNum - 1];
      if (target && target.correctIndex === -1) {
        target.correctIndex = parseAnswerKeyToken(entry.token, hasZero);
      }
    }
  }

  if (questions.length === 0) {
    return {
      ok: false,
      error:
        "Could not detect questions. Use numbered prompts (1. or Q.1), options (A-D or 1-4), and Answer: A/B/C/D (or an Answer Key at the bottom)."
    };
  }

  const fullValidation = validateQuestionSet(questions, {
    defaultTitle,
    defaultSection
  });

  if (fullValidation.ok || questions.length < 3) {
    return fullValidation;
  }

  // For larger PDF/TXT papers (3+ Qs), gracefully skip image-only / incomplete questions if most parsed cleanly.
  const validSubset = [];
  const skippedNums = [];
  for (let i = 0; i < questions.length; i += 1) {
    const single = validateQuestionSet([questions[i]], {
      defaultTitle,
      defaultSection
    });
    if (single.ok) {
      validSubset.push({ ...single.questions[0], id: `txt-q${validSubset.length + 1}` });
    } else {
      skippedNums.push(`#${i + 1}`);
    }
  }

  if (validSubset.length >= Math.ceil(questions.length / 2)) {
    const revalidated = validateQuestionSet(validSubset, {
      defaultTitle,
      defaultSection
    });
    if (revalidated.ok) {
      return {
        ...revalidated,
        skippedCount: skippedNums.length,
        warning: `Skipped ${skippedNums.length} incomplete question(s) (${skippedNums.slice(0, 5).join(", ")}${skippedNums.length > 5 ? "..." : ""}).`
      };
    }
  }

  return fullValidation;
}

/**
 * Parses a .json, .csv, or .txt file payload into one or more validated question sets.
 * Multi-paper JSON payloads ({ papers: [...] }, { sets: [...] }, or array of set objects) produce multiple sets.
 */
export function parseQuestionFile(
  rawText,
  { filename = "", defaultTitle = "", defaultSection = "Custom" } = {}
) {
  const cleanText = String(rawText || "").replace(/^\uFEFF/, "").trim();
  if (!cleanText) {
    return { ok: false, error: "File is empty." };
  }

  const baseTitle =
    defaultTitle.trim() ||
    (filename ? filename.replace(/\.(json|csv|txt|pdf)$/i, "").trim() : "") ||
    "Custom Set";

  const lowerName = filename.toLowerCase();
  const looksJson = cleanText.startsWith("[") || cleanText.startsWith("{");

  if (lowerName.endsWith(".json") || (!lowerName.endsWith(".csv") && !lowerName.endsWith(".txt") && looksJson)) {
    let parsed;
    try {
      parsed = JSON.parse(cleanText);
    } catch (err) {
      return { ok: false, error: `Invalid JSON: ${err.message}` };
    }

    // Multi-paper JSON container: { papers: [...] } or { sets: [...] }
    const multiContainer =
      parsed && !Array.isArray(parsed) && typeof parsed === "object"
        ? parsed.papers ?? parsed.sets
        : Array.isArray(parsed) && parsed.length > 0 && parsed[0] && Array.isArray(parsed[0].questions)
          ? parsed
          : null;

    if (Array.isArray(multiContainer)) {
      if (multiContainer.length === 0) {
        return { ok: false, error: "Question paper list is empty." };
      }
      const sets = [];
      for (let i = 0; i < multiContainer.length; i += 1) {
        const res = validateQuestionSet(multiContainer[i], {
          defaultTitle: `${baseTitle} · Paper ${i + 1}`,
          defaultSection
        });
        if (!res.ok) {
          return { ok: false, error: `Paper #${i + 1}: ${res.error}` };
        }
        sets.push(res);
      }
      return {
        ok: true,
        title: sets[0].title,
        section: sets[0].section,
        questions: sets[0].questions,
        sets
      };
    }

    const single = validateQuestionSet(parsed, {
      defaultTitle: baseTitle,
      defaultSection
    });
    if (!single.ok) return single;
    return { ...single, sets: [single] };
  }

  const looksCsv =
    lowerName.endsWith(".csv") ||
    (!lowerName.endsWith(".txt") && /^[^\n]*prompt|question/i.test(cleanText.split(/\r?\n/, 1)[0] || ""));

  if (looksCsv) {
    const rows = parseCsvRows(cleanText);
    if (rows.length < 2) {
      return { ok: false, error: "CSV must include a header row and at least one question row." };
    }

    const headers = rows[0].map((h) => h.toLowerCase().replace(/[\s_-]+/g, ""));
    const idxPrompt = findColumnIndex(headers, ["prompt", "question", "questiontext"]);
    const idxA = findColumnIndex(headers, ["optiona", "a", "option1"]);
    const idxB = findColumnIndex(headers, ["optionb", "b", "option2"]);
    const idxC = findColumnIndex(headers, ["optionc", "c", "option3"]);
    const idxD = findColumnIndex(headers, ["optiond", "d", "option4"]);
    const idxCorrect = findColumnIndex(headers, ["correctindex", "correct", "correctoption", "answer", "ans"]);

    if ([idxPrompt, idxA, idxB, idxC, idxD, idxCorrect].some((idx) => idx === -1)) {
      return {
        ok: false,
        error:
          "CSV header must include: prompt, optionA, optionB, optionC, optionD, correctIndex (or A/B/C/D)."
      };
    }

    const idxId = findColumnIndex(headers, ["id"]);
    const idxTopic = findColumnIndex(headers, ["topic"]);
    const idxSection = findColumnIndex(headers, ["section"]);

    const objects = rows.slice(1).map((cols, i) => ({
      id: idxId !== -1 && cols[idxId] ? cols[idxId] : `csv-q${i + 1}`,
      section: idxSection !== -1 && cols[idxSection] ? cols[idxSection] : defaultSection,
      topic: idxTopic !== -1 && cols[idxTopic] ? cols[idxTopic] : "General",
      prompt: cols[idxPrompt] ?? "",
      options: [cols[idxA] ?? "", cols[idxB] ?? "", cols[idxC] ?? "", cols[idxD] ?? ""],
      correctIndex: cols[idxCorrect] ?? ""
    }));

    const single = validateQuestionSet(objects, {
      defaultTitle: baseTitle,
      defaultSection
    });
    if (!single.ok) return single;
    return { ...single, sets: [single] };
  }

  const txtResult = parseTxtQuestionPaper(cleanText, {
    defaultTitle: baseTitle,
    defaultSection
  });
  if (!txtResult.ok) return txtResult;
  return { ...txtResult, sets: [txtResult] };
}
