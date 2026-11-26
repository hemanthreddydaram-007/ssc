import quantQuestions from "./data/quant-set-1.js";
import reasonQuestions from "./data/reason-set-1.js";
import {
  EXAM_DURATION_SEC,
  GATE_LOCK_MS,
  analyzeRun,
  computeAdaptiveTimer,
  evaluateCalibration,
  formatClock,
  formatDuration
} from "./engine.js";

const STORAGE_KEY = "ssc_chsl_trainer_v1";
const OPTION_LABELS = ["A", "B", "C", "D"];

const SECTIONS = {
  Quant: quantQuestions,
  Reasoning: reasonQuestions
};

const QUADRANT_META = {
  fastRight: { label: "Fast & Right (≤ 36s)", badgeClass: "badge-success" },
  slowRight: { label: "Slow & Right (> 36s)", badgeClass: "badge" },
  fastWrong: { label: "Fast & Wrong (≤ 36s)", badgeClass: "badge-muted" },
  slowWrong: { label: "Slow & Wrong (> 36s)", badgeClass: "badge-danger" },
  unattempted: { label: "Unattempted", badgeClass: "badge-muted" }
};

const state = {
  view: "start",
  selectedSection: "Quant",
  selectedMode: "exam",
  adaptiveEnabled: false,
  run: null,
  lastAnalysis: null,
  lastCalibration: null,
  lastRunId: null,
  inspectedIndex: null,
  clockIntervalId: null,
  gateIntervalId: null
};

const el = {
  views: {
    start: document.getElementById("view-start"),
    exam: document.getElementById("view-exam"),
    calibration: document.getElementById("view-calibration"),
    report: document.getElementById("view-report")
  },
  sectionCards: document.getElementById("section-cards"),
  modeCards: document.getElementById("mode-cards"),
  adaptiveToggle: document.getElementById("adaptive-toggle"),
  adaptiveSummary: document.getElementById("adaptive-summary"),
  btnStart: document.getElementById("btn-start"),
  btnClearHistory: document.getElementById("btn-clear-history"),
  historyContainer: document.getElementById("history-container"),

  examSectionLabel: document.getElementById("exam-section-label"),
  examModeTag: document.getElementById("exam-mode-tag"),
  examClock: document.getElementById("exam-clock"),
  btnSubmitExam: document.getElementById("btn-submit-exam"),
  examQNumber: document.getElementById("exam-q-number"),
  examQPrompt: document.getElementById("exam-q-prompt"),
  optionsWrapper: document.getElementById("options-wrapper"),
  gateOverlay: document.getElementById("gate-overlay"),
  gateCountdownText: document.getElementById("gate-countdown-text"),
  examOptions: document.getElementById("exam-options"),
  btnClear: document.getElementById("btn-clear"),
  btnSkip: document.getElementById("btn-skip"),
  btnSolveNow: document.getElementById("btn-solve-now"),
  btnSaveNext: document.getElementById("btn-save-next"),
  questionPalette: document.getElementById("question-palette"),

  calQNum: document.getElementById("cal-q-num"),
  calQTopic: document.getElementById("cal-q-topic"),
  calQStatus: document.getElementById("cal-q-status"),
  calQPrompt: document.getElementById("cal-q-prompt"),
  calChoices: document.getElementById("cal-choices"),
  calReveal: document.getElementById("cal-reveal"),
  calRevealText: document.getElementById("cal-reveal-text"),
  calRevealSub: document.getElementById("cal-reveal-sub"),
  btnToReport: document.getElementById("btn-to-report"),

  reportSubtitle: document.getElementById("report-subtitle"),
  btnRetryWeak: document.getElementById("btn-retry-weak"),
  btnHome: document.getElementById("btn-home"),
  headlineStats: document.getElementById("headline-stats"),
  calibrationRecap: document.getElementById("calibration-recap"),
  slowWrongCost: document.getElementById("slow-wrong-cost"),
  unattemptedStrip: document.getElementById("unattempted-strip"),
  inspectorPanel: document.getElementById("inspector-panel")
};

// ---------------- Storage ----------------

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveHistory(runs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(runs.slice(-50)));
  } catch {
    // Ignore storage quota errors cleanly
  }
}

function appendRunRecord(record) {
  const runs = loadHistory();
  runs.push(record);
  saveHistory(runs);
}

function updateRunCalibration(runId, calibration) {
  const runs = loadHistory();
  const target = runs.find((r) => r.id === runId);
  if (!target) return;
  target.calibration = {
    guessId: calibration.guessId,
    guessLabel: calibration.guessLabel,
    actualMs: calibration.actualMs,
    matched: calibration.matched
  };
  saveHistory(runs);
}

// ---------------- Rendering Helpers ----------------

function showView(viewName) {
  state.view = viewName;
  Object.entries(el.views).forEach(([name, node]) => {
    node.classList.toggle("hidden", name !== viewName);
  });
}

function clearTimers() {
  if (state.clockIntervalId !== null) {
    clearInterval(state.clockIntervalId);
    state.clockIntervalId = null;
  }
  if (state.gateIntervalId !== null) {
    clearInterval(state.gateIntervalId);
    state.gateIntervalId = null;
  }
}

/**
 * Safely renders question prompt text, converting pipe-delimited table blocks
 * (used in DI questions) into aligned monospace pre blocks without innerHTML.
 */
function renderPrompt(container, promptText) {
  container.textContent = "";
  const lines = String(promptText || "").split("\n");
  let index = 0;

  while (index < lines.length) {
    if (lines[index].includes("|")) {
      const tableLines = [];
      while (index < lines.length && lines[index].includes("|")) {
        tableLines.push(lines[index]);
        index += 1;
      }
      const pre = document.createElement("pre");
      pre.className = "prompt-table";
      pre.textContent = tableLines.join("\n");
      container.appendChild(pre);
    } else {
      const textLines = [];
      while (index < lines.length && !lines[index].includes("|")) {
        textLines.push(lines[index]);
        index += 1;
      }
      const span = document.createElement("span");
      span.textContent = textLines.join("\n");
      container.appendChild(span);
      if (index < lines.length) {
        container.appendChild(document.createTextNode("\n"));
      }
    }
  }
}

function getPlannedDuration() {
  if (!state.adaptiveEnabled || state.selectedMode !== "exam") {
    return {
      durationSec: EXAM_DURATION_SEC,
      label: "15:00",
      reason:
        state.selectedMode === "gate"
          ? "Fixed 15:00 warm-up drill clock"
          : "Locked 15:00 Tier 1 exam clock"
    };
  }
  return computeAdaptiveTimer(loadHistory(), state.selectedSection);
}

function renderStartView() {
  el.sectionCards.querySelectorAll("[data-section]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.section === state.selectedSection);
  });
  el.modeCards.querySelectorAll("[data-mode]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === state.selectedMode);
  });

  const adaptiveAllowed = state.selectedMode === "exam";
  el.adaptiveToggle.disabled = !adaptiveAllowed;
  if (!adaptiveAllowed && state.adaptiveEnabled) {
    state.adaptiveEnabled = false;
    el.adaptiveToggle.checked = false;
  }

  const plan = getPlannedDuration();
  el.adaptiveSummary.textContent = state.adaptiveEnabled
    ? plan.reason
    : "Enable to scale timer (17:00 / 15:00 / 13:30) from your last 2 exam runs.";
  el.btnStart.textContent = `Start ${state.selectedSection} Drill · ${plan.label}`;

  renderHistory();
}

function renderHistory() {
  const runs = loadHistory();
  el.historyContainer.textContent = "";

  if (runs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "No completed runs yet. Finish a 15-min drill to log your pace.";
    el.historyContainer.appendChild(empty);
    return;
  }

  const list = document.createElement("div");
  list.className = "history-list";

  runs
    .slice(-8)
    .reverse()
    .forEach((run) => {
      const item = document.createElement("div");
      item.className = "history-item";

      const main = document.createElement("div");
      main.className = "history-main";

      const title = document.createElement("div");
      title.className = "history-title";
      const modeText = run.mode === "gate" ? "7s Gate" : "Exam";
      const retryText = run.isRetry ? " · Retry" : "";
      title.textContent = `${run.section} (${modeText}${retryText})`;

      const meta = document.createElement("div");
      meta.className = "history-meta";
      const dateStr = new Date(run.timestamp).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
      const paceLabel = formatClock(run.durationSec * 1000);
      const panicLabel = run.panicCount > 0 ? ` · ${run.panicCount} panic` : "";
      meta.textContent = `${dateStr} · ${paceLabel} clock${panicLabel}`;

      main.append(title, meta);

      const score = document.createElement("div");
      score.className = "history-score";
      score.textContent = `${run.netScore.toFixed(2)} / ${run.maxScore}`;

      const acc = document.createElement("span");
      acc.className = "history-acc";
      acc.textContent = `${run.accuracyPct.toFixed(1)}% acc`;
      score.appendChild(acc);

      item.append(main, score);
      list.appendChild(item);
    });

  el.historyContainer.appendChild(list);
}

// ---------------- Exam Engine & Telemetry ----------------

function requestExamFullscreen() {
  try {
    if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
      Promise.resolve(document.documentElement.requestFullscreen()).catch(() => {});
    }
  } catch {
    // Fullscreen can be declined or unsupported in automated contexts
  }
}

function exitExamFullscreen() {
  try {
    if (document.fullscreenElement && document.exitFullscreen) {
      Promise.resolve(document.exitFullscreen()).catch(() => {});
    }
  } catch {
    // Ignore fullscreen exit errors
  }
}

function startRun({ questions, section, mode, durationSec, isRetry = false }) {
  clearTimers();
  const now = performance.now();
  const durationMs = durationSec * 1000;

  state.run = {
    questions,
    section,
    mode,
    isRetry,
    durationSec,
    durationMs,
    currentIndex: 0,
    answers: Array(questions.length).fill(null),
    draftOption: null,
    visited: Array(questions.length).fill(false),
    gateUnlocked: Array(questions.length).fill(mode !== "gate"),
    telemetry: questions.map(() => ({
      totalMs: 0,
      visits: 0,
      savedRemainingMs: null
    })),
    activeQuestionEnteredAt: now,
    examStartPerfMs: now,
    examEndPerfMs: now + durationMs,
    finished: false
  };

  state.run.visited[0] = true;
  state.run.telemetry[0].visits = 1;

  if (mode === "exam") {
    requestExamFullscreen();
  }

  el.examSectionLabel.textContent = `SSC CHSL Tier 1 · ${section}`;
  if (mode === "gate" || isRetry) {
    el.examModeTag.textContent = [
      mode === "gate" ? "7s Commit-or-Skip Gate" : null,
      isRetry ? `Retry Drill (${questions.length} ${questions.length === 1 ? "Q" : "Qs"})` : null
    ]
      .filter(Boolean)
      .join(" · ");
    el.examModeTag.classList.remove("hidden");
  } else {
    el.examModeTag.classList.add("hidden");
  }

  showView("exam");
  renderExamScreen();
  startClockLoop();
}

function startClockLoop() {
  const updateClock = () => {
    const run = state.run;
    if (!run || run.finished) return;
    const remainingMs = run.examEndPerfMs - performance.now();
    el.examClock.textContent = formatClock(remainingMs);
    if (remainingMs <= 0) {
      finishRun();
    }
  };
  updateClock();
  state.clockIntervalId = setInterval(updateClock, 150);
}

function flushActiveQuestionTime(now) {
  const run = state.run;
  if (!run || run.activeQuestionEnteredAt === null) return;
  const elapsed = Math.max(0, now - run.activeQuestionEnteredAt);
  run.telemetry[run.currentIndex].totalMs += elapsed;
  run.activeQuestionEnteredAt = now;
}

function commitDraftIfChanged() {
  const run = state.run;
  if (!run) return;
  const idx = run.currentIndex;
  if (run.draftOption !== null && run.draftOption !== run.answers[idx]) {
    run.answers[idx] = run.draftOption;
    run.telemetry[idx].savedRemainingMs = Math.max(0, run.examEndPerfMs - performance.now());
  }
}

function enterQuestion(targetIndex) {
  const run = state.run;
  if (!run || run.finished || targetIndex === run.currentIndex) return;

  if (state.gateIntervalId !== null) {
    clearInterval(state.gateIntervalId);
    state.gateIntervalId = null;
  }

  const now = performance.now();
  flushActiveQuestionTime(now);

  run.currentIndex = targetIndex;
  run.visited[targetIndex] = true;
  run.telemetry[targetIndex].visits += 1;
  run.activeQuestionEnteredAt = now;
  run.draftOption = run.answers[targetIndex];

  renderExamScreen();
}

function renderExamScreen() {
  const run = state.run;
  if (!run) return;

  const idx = run.currentIndex;
  const question = run.questions[idx];

  el.examQNumber.textContent = `Question ${idx + 1} of ${run.questions.length}`;
  renderPrompt(el.examQPrompt, question.prompt);
  renderExamOptions(question);
  renderPalette();
  syncGateUI();
}

function renderExamOptions(question) {
  const run = state.run;
  el.examOptions.textContent = "";

  question.options.forEach((optText, optIndex) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "option-btn";
    btn.tabIndex = -1;
    if (run.draftOption === optIndex) {
      btn.classList.add("selected");
    }

    const key = document.createElement("span");
    key.className = "option-key";
    key.textContent = OPTION_LABELS[optIndex];

    const label = document.createElement("span");
    label.textContent = optText;

    btn.append(key, label);
    btn.addEventListener("click", () => {
      if (!state.run || state.run.finished) return;
      if (!state.run.gateUnlocked[state.run.currentIndex]) return;
      state.run.draftOption = optIndex;
      renderExamOptions(question);
      btn.blur();
    });

    el.examOptions.appendChild(btn);
  });
}

function renderPalette() {
  const run = state.run;
  el.questionPalette.textContent = "";

  run.questions.forEach((_, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "palette-btn";
    btn.tabIndex = -1;
    btn.textContent = String(i + 1);

    if (run.answers[i] !== null) {
      btn.classList.add("answered");
    } else if (run.visited[i]) {
      btn.classList.add("visited");
    }

    if (i === run.currentIndex) {
      btn.classList.add("current");
    }

    btn.addEventListener("click", () => {
      if (!state.run || state.run.finished) return;
      commitDraftIfChanged();
      enterQuestion(i);
      btn.blur();
    });

    el.questionPalette.appendChild(btn);
  });
}

function syncGateUI() {
  const run = state.run;
  if (!run) return;
  const idx = run.currentIndex;
  const isUnlocked = run.gateUnlocked[idx];

  if (state.gateIntervalId !== null) {
    clearInterval(state.gateIntervalId);
    state.gateIntervalId = null;
  }

  if (isUnlocked) {
    el.optionsWrapper.classList.remove("gated");
    el.gateOverlay.classList.add("hidden");
    el.btnSolveNow.classList.add("hidden");
    el.btnClear.classList.remove("hidden");
    el.btnSaveNext.classList.remove("hidden");
    return;
  }

  el.optionsWrapper.classList.add("gated");
  el.gateOverlay.classList.remove("hidden");
  el.btnSolveNow.classList.remove("hidden");
  el.btnClear.classList.add("hidden");
  el.btnSaveNext.classList.add("hidden");

  const unlockAt = performance.now() + GATE_LOCK_MS;

  const tickGate = () => {
    const remMs = unlockAt - performance.now();
    if (remMs <= 0) {
      el.gateCountdownText.textContent = "Scan complete — Solve Now or Skip";
      el.btnSolveNow.disabled = false;
      el.btnSolveNow.textContent = "Solve Now";
      if (state.gateIntervalId !== null) {
        clearInterval(state.gateIntervalId);
        state.gateIntervalId = null;
      }
      return;
    }
    const secLeft = Math.ceil(remMs / 1000);
    el.gateCountdownText.textContent = `Scan & Judge — ${secLeft}s`;
    el.btnSolveNow.disabled = true;
    el.btnSolveNow.textContent = `Solve Now (${secLeft}s)`;
  };

  tickGate();
  state.gateIntervalId = setInterval(tickGate, 150);
}

function finishRun() {
  const run = state.run;
  if (!run || run.finished) return;
  run.finished = true;

  clearTimers();
  const now = performance.now();
  commitDraftIfChanged();
  flushActiveQuestionTime(now);
  run.activeQuestionEnteredAt = null;
  exitExamFullscreen();

  const totalElapsedMs = Math.min(run.durationMs, Math.max(0, now - run.examStartPerfMs));
  const analysis = analyzeRun({
    questions: run.questions,
    answers: run.answers,
    telemetry: run.telemetry,
    durationSec: run.durationSec,
    totalElapsedMs
  });

  state.lastAnalysis = analysis;
  state.lastCalibration = null;
  state.lastRunId = `run-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

  appendRunRecord({
    id: state.lastRunId,
    timestamp: Date.now(),
    section: run.section,
    mode: run.mode,
    isRetry: run.isRetry,
    durationSec: run.durationSec,
    totalQuestions: analysis.totalQuestions,
    attemptedCount: analysis.attemptedCount,
    correctCount: analysis.correctCount,
    wrongCount: analysis.wrongCount,
    netScore: analysis.netScore,
    maxScore: analysis.maxScore,
    accuracyPct: analysis.accuracyPct,
    panicCount: analysis.panicErrors.length,
    calibration: null
  });

  renderCalibrationView();
  showView("calibration");
}

// ---------------- Post-Test Step 1: Calibration ----------------

function renderCalibrationView() {
  const analysis = state.lastAnalysis;
  const slowest = analysis?.slowestItem;
  if (!slowest) return;

  el.calQNum.textContent = `Q${slowest.number}`;
  el.calQTopic.textContent = slowest.question.topic;
  el.calQStatus.textContent = slowest.isAttempted ? "Attempted" : "Skipped";
  renderPrompt(el.calQPrompt, slowest.question.prompt);

  el.calReveal.classList.add("hidden");
  el.calChoices.querySelectorAll("[data-guess]").forEach((btn) => {
    btn.disabled = false;
    btn.classList.remove("selected");
  });
}

function handleCalibrationGuess(guessId) {
  if (!state.lastAnalysis || state.lastCalibration) return;
  const result = evaluateCalibration(state.lastAnalysis.slowestItem, guessId);
  state.lastCalibration = result;

  if (state.lastRunId) {
    updateRunCalibration(state.lastRunId, result);
  }

  el.calChoices.querySelectorAll("[data-guess]").forEach((btn) => {
    btn.disabled = true;
    btn.classList.toggle("selected", btn.dataset.guess === guessId);
  });

  el.calRevealText.textContent = result.summaryText;
  el.calRevealSub.textContent = result.matched
    ? "Calibrated: your internal clock matched reality."
    : "Time blindness gap detected — notice how fast 36 seconds slips past under pressure.";
  el.calReveal.classList.remove("hidden");
}

// ---------------- Post-Test Step 2: 4-Quadrant Autopsy ----------------

function renderReportView() {
  const analysis = state.lastAnalysis;
  const run = state.run;
  if (!analysis || !run) return;

  el.reportSubtitle.textContent = `${run.section} · ${
    run.mode === "gate" ? "7s Gate Warm-Up" : "Pure Exam Mode"
  }${run.isRetry ? " · Weak PYQ Retry" : ""}`;

  // Headline stats
  el.headlineStats.textContent = "";
  const avgPerQ = analysis.totalQuestions > 0 ? analysis.totalElapsedMs / analysis.totalQuestions : 0;

  const cards = [
    {
      label: "Net Score",
      value: `${analysis.netScore.toFixed(2)} / ${analysis.maxScore}`,
      sub: `${analysis.correctCount} right (+${(analysis.correctCount * 2).toFixed(1)}) · ${analysis.wrongCount} wrong (−${(analysis.wrongCount * 0.5).toFixed(1)})`,
      tone: ""
    },
    {
      label: "Accuracy",
      value: `${analysis.accuracyPct.toFixed(1)}%`,
      sub: `${analysis.correctCount} correct out of ${analysis.attemptedCount} attempted (${analysis.unattemptedCount} skipped)`,
      tone: ""
    },
    {
      label: "Time Used",
      value: formatDuration(analysis.totalElapsedMs),
      sub: `Avg ${formatDuration(avgPerQ)} per question (36.0s target)`,
      tone: ""
    },
    analysis.panicErrors.length > 0
      ? {
          label: "Final-Minute Panic",
          value: `${analysis.panicErrors.length} ${analysis.panicErrors.length === 1 ? "Error" : "Errors"}`,
          sub: `Wrong in last 60s: ${analysis.panicErrors.map((e) => `Q${e.number}`).join(", ")} (−${(analysis.panicErrors.length * 0.5).toFixed(2)} marks)`,
          tone: "alert"
        }
      : {
          label: "Final-Minute Panic",
          value: "0 Errors",
          sub: "Calm finish — zero wrong answers submitted in final 60s",
          tone: "calm"
        }
  ];

  cards.forEach((card) => {
    const node = document.createElement("div");
    node.className = `stat-card ${card.tone}`.trim();
    const lbl = document.createElement("div");
    lbl.className = "stat-label";
    lbl.textContent = card.label;
    const val = document.createElement("div");
    val.className = "stat-value";
    val.textContent = card.value;
    const sub = document.createElement("div");
    sub.className = "stat-sub";
    sub.textContent = card.sub;
    node.append(lbl, val, sub);
    el.headlineStats.appendChild(node);
  });

  if (state.lastCalibration) {
    el.calibrationRecap.textContent = `Calibration check on Q${analysis.slowestItem.number}: ${state.lastCalibration.summaryText}`;
    el.calibrationRecap.classList.remove("hidden");
  } else {
    el.calibrationRecap.classList.add("hidden");
  }

  // Slow & Wrong opportunity cost
  if (analysis.quadrants.slowWrong.length > 0) {
    el.slowWrongCost.textContent = `Burned ${formatDuration(
      analysis.slowWrongTotalMs
    )} (${analysis.slowWrongTotalSec.toFixed(1)}s) → ${analysis.opportunityCostAttempts.toFixed(
      1
    )} easy attempts lost (÷ 36s)`;
    el.slowWrongCost.classList.remove("hidden");
  } else {
    el.slowWrongCost.classList.add("hidden");
  }

  // Render 4 quadrants + unattempted strip
  ["fastRight", "slowRight", "fastWrong", "slowWrong", "unattempted"].forEach((key) => {
    const items = analysis.quadrants[key];
    document.getElementById(`count-${key}`).textContent = String(items.length);
    const chipContainer = document.getElementById(`chips-${key}`);
    chipContainer.textContent = "";

    if (items.length === 0) {
      const empty = document.createElement("span");
      empty.className = "chip-empty";
      empty.textContent = "None";
      chipContainer.appendChild(empty);
      return;
    }

    items.forEach((item) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "q-chip";
      chip.dataset.index = String(item.index);
      chip.textContent = `Q${item.number} · ${formatDuration(item.totalMs)}`;
      if (item.isPanicError) {
        const panic = document.createElement("span");
        panic.className = "panic-dot";
        panic.textContent = "PANIC";
        chip.appendChild(panic);
      }
      chip.addEventListener("click", () => {
        selectInspectedQuestion(item.index);
      });
      chipContainer.appendChild(chip);
    });
  });

  el.unattemptedStrip.classList.toggle("hidden", analysis.quadrants.unattempted.length === 0);

  // One-Click Retry Loop button
  const weakCount = analysis.weakQuestions.length;
  el.btnRetryWeak.disabled = weakCount === 0;
  el.btnRetryWeak.textContent =
    weakCount > 0
      ? `Retry Wrong & Slow (>36s) · ${weakCount} ${weakCount === 1 ? "Q" : "Qs"}`
      : "Retry Wrong & Slow (>36s) · 0 Qs";

  // Auto-select first Slow & Wrong, or Slowest item for immediate inspection
  const defaultInspect =
    analysis.quadrants.slowWrong[0] ||
    analysis.weakItems[0] ||
    analysis.slowestItem ||
    analysis.items[0];
  if (defaultInspect) {
    selectInspectedQuestion(defaultInspect.index);
  }
}

function selectInspectedQuestion(itemIndex) {
  const analysis = state.lastAnalysis;
  if (!analysis) return;
  const item = analysis.items[itemIndex];
  if (!item) return;

  state.inspectedIndex = itemIndex;
  document.querySelectorAll(".q-chip").forEach((chip) => {
    chip.classList.toggle("active", Number(chip.dataset.index) === itemIndex);
  });

  el.inspectorPanel.textContent = "";

  const meta = document.createElement("div");
  meta.className = "inspector-meta";

  const qNumBadge = document.createElement("span");
  qNumBadge.className = "badge";
  qNumBadge.textContent = `Q${item.number}`;

  const topicBadge = document.createElement("span");
  topicBadge.className = "badge badge-muted";
  topicBadge.textContent = item.question.topic;

  const qMeta = QUADRANT_META[item.quadrant];
  const quadBadge = document.createElement("span");
  quadBadge.className = `badge ${qMeta.badgeClass}`;
  quadBadge.textContent = qMeta.label;

  meta.append(qNumBadge, topicBadge, quadBadge);

  if (item.isPanicError) {
    const panicBadge = document.createElement("span");
    panicBadge.className = "badge badge-danger";
    panicBadge.textContent = "Final-Minute Panic";
    meta.appendChild(panicBadge);
  }

  const timing = document.createElement("div");
  timing.className = "inspector-timing";
  const visitWord = item.visits === 1 ? "visit" : "visits";
  timing.textContent = `Time spent: ${formatDuration(item.totalMs)} (${(item.totalMs / 1000).toFixed(
    1
  )}s) across ${item.visits} ${visitWord}`;

  const promptBox = document.createElement("div");
  promptBox.className = "q-prompt compact";
  renderPrompt(promptBox, item.question.prompt);

  const optionsList = document.createElement("div");
  optionsList.className = "inspector-options";

  item.question.options.forEach((optText, optIdx) => {
    const row = document.createElement("div");
    row.className = "inspector-option";
    const isCorrectOpt = optIdx === item.question.correctIndex;
    const isUserOpt = optIdx === item.selectedIndex;

    if (isCorrectOpt) row.classList.add("correct");
    else if (isUserOpt) row.classList.add("wrong-chosen");

    const textSpan = document.createElement("span");
    textSpan.textContent = `${OPTION_LABELS[optIdx]}. ${optText}`;
    row.appendChild(textSpan);

    const tags = [];
    if (isUserOpt) tags.push("Your Answer");
    if (isCorrectOpt) tags.push("Correct");
    if (tags.length > 0) {
      const tag = document.createElement("span");
      tag.className = "opt-tag";
      tag.textContent = tags.join(" · ");
      row.appendChild(tag);
    }

    optionsList.appendChild(row);
  });

  el.inspectorPanel.append(meta, timing, promptBox, optionsList);
}

// ---------------- Event Wiring ----------------

el.sectionCards.addEventListener("click", (event) => {
  const card = event.target.closest("[data-section]");
  if (!card) return;
  state.selectedSection = card.dataset.section;
  renderStartView();
});

el.modeCards.addEventListener("click", (event) => {
  const card = event.target.closest("[data-mode]");
  if (!card) return;
  state.selectedMode = card.dataset.mode;
  renderStartView();
});

el.adaptiveToggle.addEventListener("change", () => {
  state.adaptiveEnabled = el.adaptiveToggle.checked;
  renderStartView();
});

el.btnStart.addEventListener("click", () => {
  const questions = SECTIONS[state.selectedSection];
  const plan = getPlannedDuration();
  startRun({
    questions,
    section: state.selectedSection,
    mode: state.selectedMode,
    durationSec: plan.durationSec,
    isRetry: false
  });
});

el.btnClearHistory.addEventListener("click", () => {
  saveHistory([]);
  renderStartView();
});

el.btnSolveNow.addEventListener("click", () => {
  const run = state.run;
  if (!run || run.finished) return;
  run.gateUnlocked[run.currentIndex] = true;
  syncGateUI();
  el.btnSolveNow.blur();
});

el.btnClear.addEventListener("click", () => {
  const run = state.run;
  if (!run || run.finished) return;
  const idx = run.currentIndex;
  run.draftOption = null;
  run.answers[idx] = null;
  run.telemetry[idx].savedRemainingMs = null;
  renderExamScreen();
  el.btnClear.blur();
});

el.btnSkip.addEventListener("click", () => {
  const run = state.run;
  if (!run || run.finished) return;
  const idx = run.currentIndex;
  // Discard uncommitted draft on Skip so accidental clicks aren't saved
  run.draftOption = run.answers[idx];
  const nextIdx = (idx + 1) % run.questions.length;
  if (run.questions.length === 1) {
    renderExamScreen();
  } else {
    enterQuestion(nextIdx);
  }
  el.btnSkip.blur();
});

el.btnSaveNext.addEventListener("click", () => {
  const run = state.run;
  if (!run || run.finished) return;
  const idx = run.currentIndex;
  run.answers[idx] = run.draftOption;
  run.telemetry[idx].savedRemainingMs =
    run.draftOption !== null ? Math.max(0, run.examEndPerfMs - performance.now()) : null;

  const nextIdx = (idx + 1) % run.questions.length;
  if (run.questions.length === 1) {
    renderExamScreen();
  } else {
    enterQuestion(nextIdx);
  }
  el.btnSaveNext.blur();
});

el.btnSubmitExam.addEventListener("click", () => {
  finishRun();
});

el.calChoices.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-guess]");
  if (!btn) return;
  handleCalibrationGuess(btn.dataset.guess);
});

el.btnToReport.addEventListener("click", () => {
  renderReportView();
  showView("report");
});

el.btnRetryWeak.addEventListener("click", () => {
  const analysis = state.lastAnalysis;
  const prevRun = state.run;
  if (!analysis || !prevRun || analysis.weakQuestions.length === 0) return;

  const weakQuestions = analysis.weakQuestions;
  const durationSec = Math.max(36, weakQuestions.length * 36);
  startRun({
    questions: weakQuestions,
    section: prevRun.section,
    mode: "exam",
    durationSec,
    isRetry: true
  });
});

el.btnHome.addEventListener("click", () => {
  renderStartView();
  showView("start");
});

// Mouse-only discipline during active exam / 7s gate
window.addEventListener(
  "keydown",
  (event) => {
    if (state.view !== "exam") return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    const blockedKeys = new Set([
      "Enter",
      " ",
      "Spacebar",
      "Tab",
      "ArrowUp",
      "ArrowDown",
      "ArrowLeft",
      "ArrowRight",
      "Backspace",
      "1",
      "2",
      "3",
      "4",
      "a",
      "b",
      "c",
      "d",
      "A",
      "B",
      "C",
      "D",
      "n",
      "N",
      "s",
      "S",
      "x",
      "X"
    ]);
    if (blockedKeys.has(event.key)) {
      event.preventDefault();
      event.stopPropagation();
    }
  },
  true
);

// Initialize
renderStartView();
showView("start");
