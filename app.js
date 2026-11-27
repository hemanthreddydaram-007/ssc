import { SECTION_CATALOG } from "./data/catalog.js";
import {
  QUESTION_TIME_LIMIT_MS,
  analyzeRun,
  findNextAvailableIndex,
  formatQuestionSeconds,
  getQuestionRemainingMs,
  parseQuestionFile,
  resolveTimeoutTransition,
  shuffleQuestions
} from "./engine.js";
import {
  buildOfflineMixedSet,
  buildOfflineVariantSet,
  generateQuestionsWithGemini,
  getAvailableSections,
  getAvailableTopics
} from "./generator.js";
import {
  clearAllCustomSets,
  deleteCustomSet,
  loadCustomSets,
  loadSavedGeminiKey,
  putCustomSets,
  saveGeminiKey
} from "./storage.js";
import { extractTextFromPdfFile } from "./pdf.js";

const STORAGE_KEY = "ssc_chsl_trainer_v1";
const OPTION_LABELS = ["A", "B", "C", "D"];

const SAMPLE_IMPORT_JSON = JSON.stringify(
  [
    {
      id: "sample-1",
      section: "Quant",
      topic: "Percentage",
      prompt: "If 20% of a number is 45, what is 40% of the same number?",
      options: ["60", "75", "90", "105"],
      correctIndex: 2
    },
    {
      id: "sample-2",
      section: "Reasoning",
      topic: "Number Series",
      prompt: "Find the next number in the series: 3, 6, 11, 18, 27, ?",
      options: ["36", "38", "40", "42"],
      correctIndex: 1
    }
  ],
  null,
  2
);

const SAMPLE_IMPORT_CSV = [
  "id,section,topic,prompt,optionA,optionB,optionC,optionD,correctIndex",
  'csv-1,Quant,Percentage,"If 20% of a number is 45, what is 40% of the same number?",60,75,90,105,C',
  'csv-2,Reasoning,Number Series,"Find the next number in the series: 3, 6, 11, 18, 27, ?",36,38,40,42,B'
].join("\n");

const SAMPLE_IMPORT_TXT = [
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
  "2. Find the next number in the series: 3, 6, 11, 18, 27, ?",
  "(A) 36  (B) 38  (C) 40  (D) 42",
  "Ans: B"
].join("\n");

const STATUS_META = {
  correct: { label: "Correct", badgeClass: "badge-success" },
  wrong: { label: "Wrong", badgeClass: "badge-danger" },
  unattempted: { label: "Skipped", badgeClass: "badge-muted" }
};

const state = {
  view: "start",
  customSets: [],
  selectedSectionId: SECTION_CATALOG[0].id,
  selectedSetId: SECTION_CATALOG[0].sets[0].id,
  setFilterQuery: "",
  shuffleEnabled: false,
  importOpen: false,
  generatorOpen: false,
  genSelectedIds: null, // null = all available sets
  genMode: "offline-variants",
  genSection: "ALL",
  genTopic: "ALL",
  genBusy: false,
  run: null,
  lastAnalysis: null,
  inspectedIndex: null,
  timerIntervalId: null
};

const el = {
  views: {
    start: document.getElementById("view-start"),
    exam: document.getElementById("view-exam"),
    report: document.getElementById("view-report")
  },
  sectionPanel: document.getElementById("section-panel"),
  sectionCards: document.getElementById("section-cards"),
  setFilterRow: document.getElementById("set-filter-row"),
  setFilterInput: document.getElementById("set-filter-input"),
  btnClearCustom: document.getElementById("btn-clear-custom"),
  setPills: document.getElementById("set-pills"),
  shuffleToggle: document.getElementById("shuffle-toggle"),
  directFileInput: document.getElementById("direct-file-input"),
  startImportStatus: document.getElementById("start-import-status"),
  btnOpenImport: document.getElementById("btn-open-import"),
  btnOpenGenerator: document.getElementById("btn-open-generator"),
  importDrawer: document.getElementById("import-drawer"),
  fileDropzone: document.getElementById("file-dropzone"),
  btnDownloadSampleJson: document.getElementById("btn-download-sample-json"),
  btnDownloadSampleCsv: document.getElementById("btn-download-sample-csv"),
  btnDownloadSampleTxt: document.getElementById("btn-download-sample-txt"),
  btnSampleJson: document.getElementById("btn-sample-json"),
  btnCloseImport: document.getElementById("btn-close-import"),
  importTitle: document.getElementById("import-title"),
  importFile: document.getElementById("import-file"),
  importJson: document.getElementById("import-json"),
  importFeedback: document.getElementById("import-feedback"),
  btnSaveImport: document.getElementById("btn-save-import"),

  generatorDrawer: document.getElementById("generator-drawer"),
  btnCloseGenerator: document.getElementById("btn-close-generator"),
  btnGenSelectAll: document.getElementById("btn-gen-select-all"),
  btnGenSelectImported: document.getElementById("btn-gen-select-imported"),
  btnGenSelectBuiltin: document.getElementById("btn-gen-select-builtin"),
  genSourceList: document.getElementById("gen-source-list"),
  genMode: document.getElementById("gen-mode"),
  genCount: document.getElementById("gen-count"),
  genSection: document.getElementById("gen-section"),
  genTopic: document.getElementById("gen-topic"),
  genTitle: document.getElementById("gen-title"),
  genAiBox: document.getElementById("gen-ai-box"),
  genApiKey: document.getElementById("gen-api-key"),
  genModel: document.getElementById("gen-model"),
  genRememberKey: document.getElementById("gen-remember-key"),
  btnClearKey: document.getElementById("btn-clear-key"),
  genFeedback: document.getElementById("gen-feedback"),
  btnGenerateSave: document.getElementById("btn-generate-save"),
  btnGenerateStart: document.getElementById("btn-generate-start"),

  btnStart: document.getElementById("btn-start"),
  btnClearHistory: document.getElementById("btn-clear-history"),
  historyContainer: document.getElementById("history-container"),

  examSectionLabel: document.getElementById("exam-section-label"),
  examModeTag: document.getElementById("exam-mode-tag"),
  btnSubmitExam: document.getElementById("btn-submit-exam"),
  examQNumber: document.getElementById("exam-q-number"),
  examQTimer: document.getElementById("exam-q-timer"),
  examQTimerValue: document.getElementById("exam-q-timer-value"),
  examQPrompt: document.getElementById("exam-q-prompt"),
  examOptions: document.getElementById("exam-options"),
  btnClear: document.getElementById("btn-clear"),
  btnSkip: document.getElementById("btn-skip"),
  btnSaveNext: document.getElementById("btn-save-next"),
  questionPalette: document.getElementById("question-palette"),

  reportSubtitle: document.getElementById("report-subtitle"),
  btnRetryMissed: document.getElementById("btn-retry-missed"),
  btnHome: document.getElementById("btn-home"),
  headlineStats: document.getElementById("headline-stats"),
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

function getAllSections() {
  if (state.customSets.length === 0) {
    return SECTION_CATALOG;
  }
  return [
    ...SECTION_CATALOG,
    {
      id: "Custom",
      title: "Imported & Generated Sets",
      subtitle: "Unlimited PYQ papers & generated practice sets",
      isCustom: true,
      sets: state.customSets
    }
  ];
}

function getAllAvailablePaperSets() {
  const builtin = SECTION_CATALOG.flatMap((sec) =>
    sec.sets.map((st) => ({
      ...st,
      sectionId: sec.id,
      displayLabel: `${sec.id} · ${st.label}`,
      isCustom: false
    }))
  );
  const custom = state.customSets.map((st) => ({
    ...st,
    sectionId: "Custom",
    displayLabel: st.label,
    isCustom: true
  }));
  return [...custom, ...builtin];
}

function getActiveSectionAndSet() {
  const sections = getAllSections();
  let sectionObj = sections.find((s) => s.id === state.selectedSectionId);
  if (!sectionObj) {
    sectionObj = sections[0];
    state.selectedSectionId = sectionObj.id;
  }
  let setObj = sectionObj.sets.find((st) => st.id === state.selectedSetId);
  if (!setObj) {
    setObj = sectionObj.sets[0];
    state.selectedSetId = setObj.id;
  }
  return { sections, sectionObj, setObj };
}

// ---------------- Rendering Helpers ----------------

function showView(viewName) {
  state.view = viewName;
  Object.entries(el.views).forEach(([name, node]) => {
    node.classList.toggle("hidden", name !== viewName);
  });
}

function clearTimers() {
  if (state.timerIntervalId !== null) {
    clearInterval(state.timerIntervalId);
    state.timerIntervalId = null;
  }
}

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

function setFeedbackBox(node, message, tone) {
  if (!message) {
    node.classList.add("hidden");
    node.textContent = "";
    return;
  }
  node.textContent = message;
  node.className = `import-feedback ${tone}`;
  node.classList.remove("hidden");
}

function setImportFeedback(message, tone) {
  setFeedbackBox(el.importFeedback, message, tone);
}

function setStartImportStatus(message, tone) {
  setFeedbackBox(el.startImportStatus, message, tone);
}

function setGenFeedback(message, tone) {
  setFeedbackBox(el.genFeedback, message, tone);
}

function getSelectedGeneratorSets() {
  const allSets = getAllAvailablePaperSets();
  if (state.genSelectedIds === null) {
    // Prefer imported sets by default when any exist, otherwise all built-in sets
    if (state.customSets.length > 0) {
      return allSets.filter((s) => s.isCustom);
    }
    return allSets;
  }
  return allSets.filter((s) => state.genSelectedIds.has(s.id));
}

function renderGeneratorControls() {
  el.generatorDrawer.classList.toggle("hidden", !state.generatorOpen);
  if (!state.generatorOpen) return;

  const allSets = getAllAvailablePaperSets();
  if (state.genSelectedIds === null) {
    const initial = state.customSets.length > 0 ? allSets.filter((s) => s.isCustom) : allSets;
    state.genSelectedIds = new Set(initial.map((s) => s.id));
  } else {
    // Keep only IDs that still exist
    const validIds = new Set(allSets.map((s) => s.id));
    state.genSelectedIds = new Set(Array.from(state.genSelectedIds).filter((id) => validIds.has(id)));
  }

  el.genSourceList.textContent = "";
  allSets.forEach((setItem) => {
    const checked = state.genSelectedIds.has(setItem.id);
    const chip = document.createElement("label");
    chip.className = "gen-source-chip";
    chip.classList.toggle("active", checked);

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = checked;
    cb.addEventListener("change", () => {
      if (cb.checked) state.genSelectedIds.add(setItem.id);
      else state.genSelectedIds.delete(setItem.id);
      renderGeneratorControls();
    });

    const txt = document.createElement("span");
    txt.textContent = `${setItem.displayLabel} (${setItem.questions.length})`;

    chip.append(cb, txt);
    el.genSourceList.appendChild(chip);
  });

  const selectedSets = getSelectedGeneratorSets();
  const sections = getAvailableSections(selectedSets);

  el.genSection.textContent = "";
  const allSecOpt = document.createElement("option");
  allSecOpt.value = "ALL";
  allSecOpt.textContent = "All Sections";
  el.genSection.appendChild(allSecOpt);
  sections.forEach((sec) => {
    const opt = document.createElement("option");
    opt.value = sec;
    opt.textContent = sec;
    el.genSection.appendChild(opt);
  });
  if (state.genSection !== "ALL" && !sections.includes(state.genSection)) {
    state.genSection = "ALL";
  }
  el.genSection.value = state.genSection;

  const topics = getAvailableTopics(selectedSets, state.genSection);
  el.genTopic.textContent = "";
  const allTopOpt = document.createElement("option");
  allTopOpt.value = "ALL";
  allTopOpt.textContent = "All Topics";
  el.genTopic.appendChild(allTopOpt);
  topics.forEach((topic) => {
    const opt = document.createElement("option");
    opt.value = topic;
    opt.textContent = topic;
    el.genTopic.appendChild(opt);
  });
  if (state.genTopic !== "ALL" && !topics.includes(state.genTopic)) {
    state.genTopic = "ALL";
  }
  el.genTopic.value = state.genTopic;

  el.genMode.value = state.genMode;
  el.genAiBox.classList.toggle("hidden", state.genMode !== "gemini");
  el.btnGenerateSave.disabled = state.genBusy;
  el.btnGenerateStart.disabled = state.genBusy;
}

function renderStartView() {
  const { sections, sectionObj, setObj } = getActiveSectionAndSet();

  // Section cards
  el.sectionCards.textContent = "";
  sections.forEach((sec) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice-card";
    btn.dataset.section = sec.id;
    btn.classList.toggle("active", sec.id === sectionObj.id);

    const top = document.createElement("div");
    top.className = "choice-top";

    const name = document.createElement("span");
    name.className = "choice-name";
    name.textContent = sec.title;

    const totalQs = sec.sets.reduce((sum, s) => sum + s.questions.length, 0);
    const meta = document.createElement("span");
    meta.className = "choice-meta";
    meta.textContent = `${totalQs} Qs · ${sec.sets.length} ${sec.sets.length === 1 ? "Set" : "Sets"}`;

    top.append(name, meta);

    const desc = document.createElement("p");
    desc.className = "choice-desc";
    desc.textContent = sec.subtitle;

    btn.append(top, desc);
    el.sectionCards.appendChild(btn);
  });

  // Custom set search & clear controls
  const showFilter = Boolean(sectionObj.isCustom) && sectionObj.sets.length > 0;
  el.setFilterRow.classList.toggle("hidden", !showFilter);
  el.setFilterInput.classList.toggle("hidden", sectionObj.sets.length <= 4);
  if (!showFilter) {
    state.setFilterQuery = "";
    el.setFilterInput.value = "";
  }

  const query = state.setFilterQuery.trim().toLowerCase();
  const visibleSets = sectionObj.isCustom && query
    ? sectionObj.sets.filter((st) => st.label.toLowerCase().includes(query))
    : sectionObj.sets;

  // Set pills
  el.setPills.textContent = "";
  visibleSets.forEach((st) => {
    const wrap = document.createElement("div");
    wrap.className = "set-pill-wrap";
    wrap.classList.toggle("active", st.id === setObj.id);

    const pillBtn = document.createElement("button");
    pillBtn.type = "button";
    pillBtn.className = "set-pill-btn";
    pillBtn.textContent = `${st.label} (${st.questions.length} Qs)`;
    pillBtn.addEventListener("click", () => {
      state.selectedSetId = st.id;
      renderStartView();
    });
    wrap.appendChild(pillBtn);

    if (st.isCustom) {
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "set-delete-btn";
      delBtn.title = `Delete ${st.label}`;
      delBtn.setAttribute("aria-label", `Delete ${st.label}`);
      delBtn.textContent = "×";
      delBtn.addEventListener("click", async () => {
        await deleteCustomSet(st.id);
        state.customSets = state.customSets.filter((item) => item.id !== st.id);
        if (state.genSelectedIds) state.genSelectedIds.delete(st.id);
        if (state.customSets.length === 0) {
          state.selectedSectionId = SECTION_CATALOG[0].id;
          state.selectedSetId = SECTION_CATALOG[0].sets[0].id;
        }
        renderStartView();
      });
      wrap.appendChild(delBtn);
    }

    el.setPills.appendChild(wrap);
  });

  el.shuffleToggle.checked = state.shuffleEnabled;
  el.importDrawer.classList.toggle("hidden", !state.importOpen);
  renderGeneratorControls();

  const shortSection = sectionObj.isCustom ? setObj.label : sectionObj.id;
  const qCount = setObj.questions.length;
  el.btnStart.textContent = `Start ${shortSection} · ${qCount} ${qCount === 1 ? "Q" : "Qs"} (35s / Q)`;

  renderHistory();
}

async function persistNewSets(validations, { selectFirst = true } = {}) {
  const baseTs = Date.now();
  const created = validations.map((v, idx) => ({
    id: `custom-${baseTs.toString(36)}-${idx}-${Math.random().toString(36).slice(2, 6)}`,
    label: v.title,
    isCustom: true,
    createdAt: baseTs + idx,
    questions: v.questions
  }));

  await putCustomSets(created);
  state.customSets.push(...created);

  if (state.genSelectedIds !== null) {
    created.forEach((s) => state.genSelectedIds.add(s.id));
  }

  if (selectFirst && created.length > 0) {
    state.selectedSectionId = "Custom";
    state.selectedSetId = created[created.length - 1].id;
  }

  return created;
}

async function importFilesFromExplorer(fileList) {
  const files = Array.from(fileList || []);
  if (files.length === 0) return;

  const allValidations = [];

  for (const file of files) {
    const isPdf =
      file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf";
    let text = "";
    try {
      if (isPdf) {
        setStartImportStatus(`Extracting text from "${file.name}"...`, "success");
        text = await extractTextFromPdfFile(file);
        if (!text.trim()) {
          state.importOpen = true;
          renderStartView();
          setStartImportStatus("", "");
          setImportFeedback(
            `No selectable text found in "${file.name}" (it may be a scanned/image PDF). Use a text-based PDF or .txt/.csv/.json.`,
            "error"
          );
          return;
        }
      } else {
        text = await file.text();
      }
    } catch (err) {
      state.importOpen = true;
      renderStartView();
      setStartImportStatus("", "");
      setImportFeedback(
        err?.message ? `${file.name}: ${err.message}` : `Could not read "${file.name}".`,
        "error"
      );
      return;
    }

    const explicitTitle = files.length === 1 ? el.importTitle.value.trim() : "";
    const validation = parseQuestionFile(text, {
      filename: file.name,
      defaultTitle: explicitTitle,
      defaultSection: "Custom"
    });

    if (!validation.ok) {
      state.importOpen = true;
      el.importJson.value = text;
      if (!el.importTitle.value.trim()) {
        el.importTitle.value = file.name.replace(/\.(json|csv|txt|pdf)$/i, "");
      }
      renderStartView();
      setStartImportStatus("", "");
      setImportFeedback(`${file.name}: ${validation.error}`, "error");
      return;
    }

    const parsedSets = validation.sets || [validation];
    allValidations.push(...parsedSets);
  }

  const savedSets = await persistNewSets(allValidations);
  const totalQuestions = savedSets.reduce((sum, s) => sum + s.questions.length, 0);

  state.importOpen = false;
  el.importTitle.value = "";
  el.importJson.value = "";
  setImportFeedback("", "");
  renderStartView();

  const warnings = allValidations.map((s) => s.warning).filter(Boolean);
  const warningSuffix = warnings.length > 0 ? ` (${warnings[0]})` : "";
  const statusMsg =
    savedSets.length === 1
      ? `Imported "${savedSets[0].label}" (${totalQuestions} ${totalQuestions === 1 ? "Q" : "Qs"}).${warningSuffix}`
      : `Imported ${savedSets.length} papers (${totalQuestions} Qs total).${warningSuffix}`;
  setStartImportStatus(statusMsg, "success");
}

function downloadSampleFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderHistory() {
  const runs = loadHistory();
  el.historyContainer.textContent = "";

  if (runs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "No completed runs yet. Finish a drill to log your score.";
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
      const setTag = run.setLabel ? ` · ${run.setLabel}` : "";
      const retryText = run.isRetry ? " · Retry" : "";
      title.textContent = `${run.section}${setTag}${retryText}`;

      const meta = document.createElement("div");
      meta.className = "history-meta";
      const dateStr = new Date(run.timestamp).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
      meta.textContent = `${dateStr} · ${run.totalQuestions} Qs · 35s/Q`;

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

// ---------------- 35s Per-Question Engine ----------------

function startRun({
  questions,
  section,
  setLabel = "",
  isRetry = false,
  isCustom = false
}) {
  clearTimers();
  const now = performance.now();

  state.run = {
    questions,
    section,
    setLabel,
    isRetry,
    isCustom,
    currentIndex: 0,
    answers: Array(questions.length).fill(null),
    draftOption: null,
    visited: Array(questions.length).fill(false),
    expired: Array(questions.length).fill(false),
    spentMs: Array(questions.length).fill(0),
    activeQuestionEnteredAt: now,
    finished: false
  };

  state.run.visited[0] = true;

  const labelSuffix = setLabel ? ` · ${setLabel}` : "";
  el.examSectionLabel.textContent = `SSC CHSL Tier 1 · ${section}${labelSuffix}`;

  if (isRetry) {
    el.examModeTag.textContent = `Retry Drill (${questions.length} ${questions.length === 1 ? "Q" : "Qs"})`;
    el.examModeTag.classList.remove("hidden");
  } else {
    el.examModeTag.classList.add("hidden");
  }

  showView("exam");
  renderExamScreen(now);
  startQuestionTimerLoop();
}

function updateQuestionTimerUI(now = performance.now(), remainingOverride = null) {
  const run = state.run;
  if (!run) return;

  const remainingMs =
    remainingOverride ??
    getQuestionRemainingMs({
      totalMs: run.spentMs[run.currentIndex],
      activeEnteredAt: run.activeQuestionEnteredAt,
      now,
      limitMs: QUESTION_TIME_LIMIT_MS
    });

  const secLeft = Math.ceil(Math.max(0, remainingMs) / 1000);
  el.examQTimerValue.textContent = formatQuestionSeconds(remainingMs);
  el.examQTimer.classList.toggle("warning", secLeft > 5 && secLeft <= 10);
  el.examQTimer.classList.toggle("critical", secLeft <= 5);
}

function handleQuestionTimeout(now) {
  const run = state.run;
  if (!run || run.finished) return;

  const idx = run.currentIndex;
  commitDraft();
  run.spentMs[idx] = QUESTION_TIME_LIMIT_MS;
  run.activeQuestionEnteredAt = now;
  run.expired[idx] = true;

  const decision = resolveTimeoutTransition({
    currentIndex: idx,
    totalQuestions: run.questions.length,
    expired: run.expired,
    visited: run.visited,
    answers: run.answers
  });

  if (decision.action === "finish") {
    finishRun();
    return;
  }

  enterQuestion(decision.nextIndex, now);
}

function startQuestionTimerLoop() {
  const tick = () => {
    const run = state.run;
    if (!run || run.finished) return;
    const now = performance.now();
    const qRemainingMs = getQuestionRemainingMs({
      totalMs: run.spentMs[run.currentIndex],
      activeEnteredAt: run.activeQuestionEnteredAt,
      now,
      limitMs: QUESTION_TIME_LIMIT_MS
    });
    updateQuestionTimerUI(now, qRemainingMs);
    if (qRemainingMs <= 0) {
      handleQuestionTimeout(now);
    }
  };
  tick();
  state.timerIntervalId = setInterval(tick, 100);
}

function flushActiveQuestionTime(now) {
  const run = state.run;
  if (!run || run.activeQuestionEnteredAt === null) return;
  const idx = run.currentIndex;
  const elapsed = Math.max(0, now - run.activeQuestionEnteredAt);
  run.spentMs[idx] = Math.min(QUESTION_TIME_LIMIT_MS, run.spentMs[idx] + elapsed);
  run.activeQuestionEnteredAt = now;
}

function commitDraft() {
  const run = state.run;
  if (!run) return;
  const idx = run.currentIndex;
  if (run.draftOption !== null && run.draftOption !== run.answers[idx]) {
    run.answers[idx] = run.draftOption;
  }
}

function enterQuestion(targetIndex, nowOverride = null) {
  const run = state.run;
  if (!run || run.finished || targetIndex === run.currentIndex || run.expired[targetIndex]) return;

  const now = nowOverride ?? performance.now();
  flushActiveQuestionTime(now);

  run.currentIndex = targetIndex;
  run.visited[targetIndex] = true;
  run.activeQuestionEnteredAt = now;
  run.draftOption = run.answers[targetIndex];

  renderExamScreen(now);
}

function renderExamScreen(now = performance.now()) {
  const run = state.run;
  if (!run) return;

  const idx = run.currentIndex;
  const question = run.questions[idx];

  el.examQNumber.textContent = `Question ${idx + 1} of ${run.questions.length}`;
  updateQuestionTimerUI(now);
  renderPrompt(el.examQPrompt, question.prompt);
  renderExamOptions(question);
  renderPalette();
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

    if (run.expired[i]) {
      btn.classList.add("expired");
      btn.disabled = true;
      btn.title = "35s limit used";
    }

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
      if (state.run.expired[i] || i === state.run.currentIndex) return;
      commitDraft();
      enterQuestion(i);
      btn.blur();
    });

    el.questionPalette.appendChild(btn);
  });
}

function finishRun() {
  const run = state.run;
  if (!run || run.finished) return;
  run.finished = true;

  clearTimers();
  commitDraft();
  run.activeQuestionEnteredAt = null;

  const analysis = analyzeRun({
    questions: run.questions,
    answers: run.answers
  });

  state.lastAnalysis = analysis;

  appendRunRecord({
    id: `run-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    timestamp: Date.now(),
    section: run.section,
    setLabel: run.setLabel,
    isRetry: run.isRetry,
    isCustom: run.isCustom,
    totalQuestions: analysis.totalQuestions,
    attemptedCount: analysis.attemptedCount,
    correctCount: analysis.correctCount,
    wrongCount: analysis.wrongCount,
    netScore: analysis.netScore,
    maxScore: analysis.maxScore,
    accuracyPct: analysis.accuracyPct
  });

  renderReportView();
  showView("report");
}

// ---------------- Results View ----------------

function renderReportView() {
  const analysis = state.lastAnalysis;
  const run = state.run;
  if (!analysis || !run) return;

  const setPart = run.setLabel ? ` · ${run.setLabel}` : "";
  el.reportSubtitle.textContent = `${run.section}${setPart}${run.isRetry ? " · Retry Drill" : ""}`;

  el.headlineStats.textContent = "";
  const cards = [
    {
      label: "Net Score",
      value: `${analysis.netScore.toFixed(2)} / ${analysis.maxScore}`,
      sub: `${analysis.correctCount} right (+${(analysis.correctCount * 2).toFixed(1)}) · ${analysis.wrongCount} wrong (−${(analysis.wrongCount * 0.5).toFixed(1)})`
    },
    {
      label: "Accuracy",
      value: `${analysis.accuracyPct.toFixed(1)}%`,
      sub: `${analysis.correctCount} correct out of ${analysis.attemptedCount} attempted`
    },
    {
      label: "Question Breakdown",
      value: `${analysis.correctCount} / ${analysis.totalQuestions}`,
      sub: `${analysis.wrongCount} wrong · ${analysis.unattemptedCount} skipped`
    }
  ];

  cards.forEach((card) => {
    const node = document.createElement("div");
    node.className = "stat-card";
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

  ["correct", "wrong", "unattempted"].forEach((key) => {
    const items = analysis.groups[key];
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
      chip.textContent = `Q${item.number}`;
      chip.addEventListener("click", () => {
        selectInspectedQuestion(item.index);
      });
      chipContainer.appendChild(chip);
    });
  });

  const missedCount = analysis.missedQuestions.length;
  el.btnRetryMissed.disabled = missedCount === 0;
  el.btnRetryMissed.textContent =
    missedCount > 0
      ? `Retry Wrong & Skipped · ${missedCount} ${missedCount === 1 ? "Q" : "Qs"}`
      : "Retry Wrong & Skipped · 0 Qs";

  const defaultInspect =
    analysis.groups.wrong[0] ||
    analysis.groups.unattempted[0] ||
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

  const sMeta = STATUS_META[item.status];
  const statusBadge = document.createElement("span");
  statusBadge.className = `badge ${sMeta.badgeClass}`;
  statusBadge.textContent = sMeta.label;

  meta.append(qNumBadge, topicBadge, statusBadge);

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

  el.inspectorPanel.append(meta, promptBox, optionsList);
}

// ---------------- Generator Flow ----------------

async function runQuestionGeneration({ startImmediately = false } = {}) {
  const sourceSets = getSelectedGeneratorSets();
  if (sourceSets.length === 0) {
    setGenFeedback("Select at least one source PYQ paper above.", "error");
    return;
  }

  const count = Math.max(1, Math.min(200, Number(el.genCount.value) || 25));
  const customTitle = el.genTitle.value.trim();
  const modeLabel =
    state.genMode === "offline-variants"
      ? "Generated Variants"
      : state.genMode === "offline-mix"
        ? "PYQ Mix"
        : "AI Generated";
  const filterTag =
    state.genTopic !== "ALL"
      ? state.genTopic
      : state.genSection !== "ALL"
        ? state.genSection
        : `${count} Qs`;
  const title = customTitle || `${modeLabel} · ${filterTag}`;

  let result;
  if (state.genMode === "offline-mix") {
    result = buildOfflineMixedSet({
      sourceSets,
      sectionFilter: state.genSection,
      topicFilter: state.genTopic,
      count
    });
  } else if (state.genMode === "offline-variants") {
    result = buildOfflineVariantSet({
      sourceSets,
      sectionFilter: state.genSection,
      topicFilter: state.genTopic,
      count
    });
  } else {
    const apiKey = el.genApiKey.value.trim();
    if (el.genRememberKey.checked && apiKey) {
      saveGeminiKey(apiKey);
    }
    state.genBusy = true;
    setGenFeedback("Generating questions with Gemini API...", "success");
    renderGeneratorControls();

    result = await generateQuestionsWithGemini({
      apiKey,
      model: el.genModel.value.trim() || "gemini-2.5-flash",
      sourceSets,
      sectionFilter: state.genSection,
      topicFilter: state.genTopic,
      count,
      title
    });

    state.genBusy = false;
    renderGeneratorControls();
  }

  if (!result.ok) {
    setGenFeedback(result.error, "error");
    return;
  }

  const [saved] = await persistNewSets([
    {
      title: result.title || title,
      section: "Custom",
      questions: result.questions
    }
  ]);

  el.genTitle.value = "";
  setGenFeedback(result.summary, "success");
  setStartImportStatus(`Saved "${saved.label}" (${saved.questions.length} Qs). ${result.summary}`, "success");
  renderStartView();

  if (startImmediately) {
    const prepared = state.shuffleEnabled ? shuffleQuestions(saved.questions) : [...saved.questions];
    startRun({
      questions: prepared,
      section: "Custom",
      setLabel: saved.label,
      isRetry: false,
      isCustom: true
    });
  }
}

// ---------------- Event Wiring ----------------

el.sectionCards.addEventListener("click", (event) => {
  const card = event.target.closest("[data-section]");
  if (!card) return;
  state.selectedSectionId = card.dataset.section;
  const sections = getAllSections();
  const nextSec = sections.find((s) => s.id === state.selectedSectionId);
  if (nextSec && nextSec.sets.length > 0) {
    state.selectedSetId = nextSec.sets[0].id;
  }
  renderStartView();
});

el.setFilterInput.addEventListener("input", () => {
  state.setFilterQuery = el.setFilterInput.value;
  renderStartView();
});

el.btnClearCustom.addEventListener("click", async () => {
  await clearAllCustomSets();
  state.customSets = [];
  state.genSelectedIds = null;
  state.selectedSectionId = SECTION_CATALOG[0].id;
  state.selectedSetId = SECTION_CATALOG[0].sets[0].id;
  setStartImportStatus("Cleared all imported & generated sets.", "success");
  renderStartView();
});

el.shuffleToggle.addEventListener("change", () => {
  state.shuffleEnabled = el.shuffleToggle.checked;
});

el.btnOpenImport.addEventListener("click", () => {
  state.importOpen = !state.importOpen;
  if (state.importOpen) state.generatorOpen = false;
  setImportFeedback("", "");
  setStartImportStatus("", "");
  renderStartView();
});

el.btnCloseImport.addEventListener("click", () => {
  state.importOpen = false;
  setImportFeedback("", "");
  renderStartView();
});

el.btnOpenGenerator.addEventListener("click", () => {
  state.generatorOpen = !state.generatorOpen;
  if (state.generatorOpen) state.importOpen = false;
  setGenFeedback("", "");
  renderStartView();
});

el.btnCloseGenerator.addEventListener("click", () => {
  state.generatorOpen = false;
  setGenFeedback("", "");
  renderStartView();
});

el.btnGenSelectAll.addEventListener("click", () => {
  state.genSelectedIds = new Set(getAllAvailablePaperSets().map((s) => s.id));
  renderGeneratorControls();
});

el.btnGenSelectImported.addEventListener("click", () => {
  const imported = getAllAvailablePaperSets().filter((s) => s.isCustom);
  state.genSelectedIds = new Set(imported.map((s) => s.id));
  renderGeneratorControls();
});

el.btnGenSelectBuiltin.addEventListener("click", () => {
  const builtin = getAllAvailablePaperSets().filter((s) => !s.isCustom);
  state.genSelectedIds = new Set(builtin.map((s) => s.id));
  renderGeneratorControls();
});

el.genMode.addEventListener("change", () => {
  state.genMode = el.genMode.value;
  setGenFeedback("", "");
  renderGeneratorControls();
});

el.genSection.addEventListener("change", () => {
  state.genSection = el.genSection.value;
  state.genTopic = "ALL";
  renderGeneratorControls();
});

el.genTopic.addEventListener("change", () => {
  state.genTopic = el.genTopic.value;
});

el.btnClearKey.addEventListener("click", () => {
  saveGeminiKey("");
  el.genApiKey.value = "";
  el.genRememberKey.checked = false;
  setGenFeedback("Cleared saved Gemini API key.", "success");
});

el.btnGenerateSave.addEventListener("click", () => {
  runQuestionGeneration({ startImmediately: false });
});

el.btnGenerateStart.addEventListener("click", () => {
  runQuestionGeneration({ startImmediately: true });
});

el.btnDownloadSampleJson.addEventListener("click", () => {
  downloadSampleFile("sample-chsl-set.json", SAMPLE_IMPORT_JSON, "application/json");
});

el.btnDownloadSampleCsv.addEventListener("click", () => {
  downloadSampleFile("sample-chsl-set.csv", SAMPLE_IMPORT_CSV, "text/csv");
});

el.btnDownloadSampleTxt.addEventListener("click", () => {
  downloadSampleFile("sample-chsl-set.txt", SAMPLE_IMPORT_TXT, "text/plain");
});

el.btnSampleJson.addEventListener("click", () => {
  if (!el.importTitle.value.trim()) {
    el.importTitle.value = "Sample Custom Drill";
  }
  el.importJson.value = SAMPLE_IMPORT_JSON;
  setImportFeedback("Loaded 2-question sample template. Click Validate & Save Pasted Paper to import.", "success");
});

el.directFileInput.addEventListener("change", async () => {
  await importFilesFromExplorer(el.directFileInput.files);
  el.directFileInput.value = "";
});

el.importFile.addEventListener("change", async () => {
  await importFilesFromExplorer(el.importFile.files);
  el.importFile.value = "";
});

function wireDropTarget(targetNode) {
  targetNode.addEventListener("dragover", (event) => {
    event.preventDefault();
    targetNode.classList.add("drag-over");
  });
  targetNode.addEventListener("dragleave", (event) => {
    if (!targetNode.contains(event.relatedTarget)) {
      targetNode.classList.remove("drag-over");
    }
  });
  targetNode.addEventListener("drop", async (event) => {
    event.preventDefault();
    targetNode.classList.remove("drag-over");
    if (event.dataTransfer?.files?.length) {
      await importFilesFromExplorer(event.dataTransfer.files);
    }
  });
}

wireDropTarget(el.sectionPanel);
wireDropTarget(el.fileDropzone);

el.btnSaveImport.addEventListener("click", async () => {
  const customTitle = el.importTitle.value.trim() || `Custom Paper ${state.customSets.length + 1}`;
  const validation = parseQuestionFile(el.importJson.value, {
    defaultTitle: customTitle,
    defaultSection: "Custom"
  });

  if (!validation.ok) {
    setImportFeedback(validation.error, "error");
    return;
  }

  const parsedSets = validation.sets || [validation];
  const savedSets = await persistNewSets(parsedSets);
  const totalQuestions = savedSets.reduce((sum, s) => sum + s.questions.length, 0);

  state.importOpen = false;
  el.importTitle.value = "";
  el.importJson.value = "";
  setImportFeedback("", "");
  renderStartView();
  setStartImportStatus(
    savedSets.length === 1
      ? `Imported "${savedSets[0].label}" (${totalQuestions} ${totalQuestions === 1 ? "Q" : "Qs"}).`
      : `Imported ${savedSets.length} papers (${totalQuestions} Qs total).`,
    "success"
  );
});

el.btnStart.addEventListener("click", () => {
  const { sectionObj, setObj } = getActiveSectionAndSet();
  const preparedQuestions = state.shuffleEnabled
    ? shuffleQuestions(setObj.questions)
    : [...setObj.questions];

  startRun({
    questions: preparedQuestions,
    section: sectionObj.id,
    setLabel: setObj.label,
    isRetry: false,
    isCustom: Boolean(sectionObj.isCustom)
  });
});

el.btnClearHistory.addEventListener("click", () => {
  saveHistory([]);
  renderStartView();
});

el.btnClear.addEventListener("click", () => {
  const run = state.run;
  if (!run || run.finished) return;
  const idx = run.currentIndex;
  run.draftOption = null;
  run.answers[idx] = null;
  renderExamScreen();
  el.btnClear.blur();
});

function advanceToNextAvailable(idx) {
  const run = state.run;
  const nextIdx = findNextAvailableIndex({
    currentIndex: idx,
    totalQuestions: run.questions.length,
    expired: run.expired
  });
  if (nextIdx === null) {
    renderExamScreen();
  } else {
    enterQuestion(nextIdx);
  }
}

el.btnSkip.addEventListener("click", () => {
  const run = state.run;
  if (!run || run.finished) return;
  const idx = run.currentIndex;
  run.draftOption = run.answers[idx];
  advanceToNextAvailable(idx);
  el.btnSkip.blur();
});

el.btnSaveNext.addEventListener("click", () => {
  const run = state.run;
  if (!run || run.finished) return;
  const idx = run.currentIndex;
  run.answers[idx] = run.draftOption;
  advanceToNextAvailable(idx);
  el.btnSaveNext.blur();
});

el.btnSubmitExam.addEventListener("click", () => {
  finishRun();
});

el.btnRetryMissed.addEventListener("click", () => {
  const analysis = state.lastAnalysis;
  const prevRun = state.run;
  if (!analysis || !prevRun || analysis.missedQuestions.length === 0) return;

  startRun({
    questions: analysis.missedQuestions,
    section: prevRun.section,
    setLabel: prevRun.setLabel,
    isRetry: true,
    isCustom: prevRun.isCustom
  });
});

el.btnHome.addEventListener("click", () => {
  renderStartView();
  showView("start");
});

// Mouse-only discipline during active drill
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
async function init() {
  const savedKey = loadSavedGeminiKey();
  if (savedKey) {
    el.genApiKey.value = savedKey;
    el.genRememberKey.checked = true;
  }
  state.customSets = await loadCustomSets();
  renderStartView();
  showView("start");
}

init();
