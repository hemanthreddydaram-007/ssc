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

function parseInlineOptionsLine(line) {
  const match = line.match(
    /^\s*(?:\(?A\)?[.)\]:-]?)\s+(.+?)\s+(?:\(?B\)?[.)\]:-])\s+(.+?)\s+(?:\(?C\)?[.)\]:-])\s+(.+?)\s+(?:\(?D\)?[.)\]:-])\s+(.+?)\s*$/i
  );
  if (!match) return null;
  return [match[1].trim(), match[2].trim(), match[3].trim(), match[4].trim()];
}

/**
 * Parses a plain-text (.txt) previous-year question paper into a validated set.
 * Supports numbered questions (1., Q1., Q.1, Question 1:), A/B/C/D options (line-by-line or inline),
 * Answer:/Ans:/Key: lines, and optional Section:/Topic: lines.
 */
export function parseTxtQuestionPaper(
  rawText,
  { defaultTitle = "Custom Set", defaultSection = "Custom" } = {}
) {
  const lines = String(rawText || "").replace(/^\uFEFF/, "").split(/\r?\n/);
  const questions = [];
  let currentSection = defaultSection;
  let currentTopic = "General";
  let current = null;

  const flushCurrent = () => {
    if (!current) return;
    const prompt = current.promptLines.join("\n").trim();
    const opts = ["A", "B", "C", "D"].map((k) => current.options[k] || "");
    const ans = parseCorrectOptionValue(current.answerRaw, opts);
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
    const line = rawLine.trim();
    if (!line) {
      if (current && !current.startedOptions && current.promptLines.length > 0) {
        current.promptLines.push("");
      }
      continue;
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

    const qStart = line.match(/^(?:Question\s*\d+|Q\.?\s*\d+|\d+)\s*[.):\-]\s+(.+)$/i);
    if (qStart && (!current || current.startedOptions || current.answerRaw !== "")) {
      flushCurrent();
      current = {
        section: currentSection,
        topic: currentTopic,
        promptLines: [qStart[1].trim()],
        options: {},
        startedOptions: false,
        answerRaw: ""
      };
      continue;
    }

    if (!current) {
      continue;
    }

    const ansMatch = line.match(/^(?:Answer|Ans|Correct(?:\s*Answer|\s*Option)?|Key)\s*[.:=\-]\s*(.+)$/i);
    if (ansMatch) {
      current.answerRaw = ansMatch[1].trim();
      continue;
    }

    const inlineOpts = parseInlineOptionsLine(line);
    if (inlineOpts) {
      current.startedOptions = true;
      current.options = { A: inlineOpts[0], B: inlineOpts[1], C: inlineOpts[2], D: inlineOpts[3] };
      continue;
    }

    const optMatch = line.match(/^\(?([ABCD])\)?\s*[.):\-]\s+(.+)$/i);
    if (optMatch) {
      current.startedOptions = true;
      current.options[optMatch[1].toUpperCase()] = optMatch[2].trim();
      continue;
    }

    if (!current.startedOptions) {
      current.promptLines.push(line);
    }
  }

  flushCurrent();

  if (questions.length === 0) {
    return {
      ok: false,
      error:
        "Could not detect questions in .txt file. Use numbered prompts (1. ...), A)/B)/C)/D) options, and Answer: A/B/C/D."
    };
  }

  return validateQuestionSet(questions, {
    defaultTitle,
    defaultSection
  });
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
    (filename ? filename.replace(/\.(json|csv|txt)$/i, "").trim() : "") ||
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
