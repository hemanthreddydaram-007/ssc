import { startTestAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import {
  getDocument,
  uploadDocumentFile,
  type DocumentItem,
} from "@/lib/api/documents";
import {
  extractKnowledge,
  getDocumentKnowledge,
} from "@/lib/api/knowledge";
import {
  getJob,
  isTerminalJobStatus,
  processDocument,
  type ProcessingJobOut,
} from "@/lib/api/jobs";
import {
  generateDocumentNotes,
  listDocumentNotes,
  type NoteSummaryOut,
  type NoteType,
} from "@/lib/api/notes";
import {
  generateQuestions,
  listDocumentQuestions,
} from "@/lib/api/questions";
import {
  createTest,
  type TimerMode,
} from "@/lib/api/tests";

export interface PdfPipelineProgress {
  stepLabel: string;
  detail: string;
  percent: number;
  documentId?: string;
}

type ProgressCallback = (progress: PdfPipelineProgress) => void;

const EXTRACTED_STATUSES = new Set([
  "extracted",
  "knowledge_ready",
  "notes_ready",
  "ready",
]);

const KNOWLEDGE_READY_STATUSES = new Set([
  "knowledge_ready",
  "notes_ready",
  "ready",
]);

function sleepWithSignal(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("The operation was aborted.", "AbortError"));
      return;
    }
    const timer = globalThis.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      globalThis.clearTimeout(timer);
      reject(new DOMException("The operation was aborted.", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Poll a processing job until it reaches a terminal state, forwarding live progress.
 */
export async function waitForJobCompletion(
  jobId: string,
  options: {
    basePercent: number;
    spanPercent: number;
    stepLabel: string;
    documentId?: string;
    onProgress?: ProgressCallback;
    signal?: AbortSignal;
    pollIntervalMs?: number;
  },
): Promise<ProcessingJobOut> {
  const interval = options.pollIntervalMs ?? 1800;

  while (true) {
    if (options.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }
    const job = await getJob(jobId, options.signal);
    const jobPct = Math.max(0, Math.min(100, job.progress_percent ?? 0));
    const overallPct = Math.min(
      99,
      Math.round(options.basePercent + (jobPct / 100) * options.spanPercent),
    );
    const detail =
      job.total_items > 0
        ? `${job.processed_items} / ${job.total_items} items processed`
        : "Working…";

    options.onProgress?.({
      stepLabel: options.stepLabel,
      detail,
      percent: overallPct,
      documentId: options.documentId,
    });

    if (isTerminalJobStatus(job.status)) {
      if (job.status.toLowerCase() === "failed") {
        throw new Error(
          job.error_message || `${options.stepLabel} failed. Please try again.`,
        );
      }
      return job;
    }

    await sleepWithSignal(interval, options.signal);
  }
}

/**
 * Upload a file or transparently reuse the existing server document if a 409 duplicate occurs.
 */
export async function uploadOrReusePdf(params: {
  file: File;
  title?: string;
  examConfigId?: string | null;
  subjectCode?: string | null;
  materialType?: string;
  language?: string;
  onProgress?: ProgressCallback;
  signal?: AbortSignal;
}): Promise<DocumentItem> {
  params.onProgress?.({
    stepLabel: "Uploading PDF",
    detail: params.file.name,
    percent: 8,
  });

  try {
    return await uploadDocumentFile({
      file: params.file,
      title: params.title || undefined,
      exam_config_id: params.examConfigId ?? null,
      subject_code: params.subjectCode ?? null,
      material_type: params.materialType ?? "other",
      language: params.language ?? "en",
      onProgress: (pct) => {
        params.onProgress?.({
          stepLabel: "Uploading PDF",
          detail: `${pct}% uploaded`,
          percent: Math.max(5, Math.round(pct * 0.15)),
        });
      },
    });
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status === 409 &&
      error.existingDocumentId
    ) {
      params.onProgress?.({
        stepLabel: "Found existing PDF",
        detail: "Continuing with your uploaded copy in library…",
        percent: 18,
        documentId: error.existingDocumentId,
      });
      return getDocument(error.existingDocumentId, params.signal);
    }
    throw error;
  }
}

/**
 * Ensure a PDF is extracted and has knowledge/topics ready before generating notes or questions.
 */
export async function ensureDocumentKnowledgeReady(params: {
  file?: File | null;
  documentId?: string;
  examConfigId?: string | null;
  onProgress?: ProgressCallback;
  signal?: AbortSignal;
}): Promise<{ document: DocumentItem; topicCount: number }> {
  let doc: DocumentItem;
  if (params.documentId) {
    params.onProgress?.({
      stepLabel: "Loading PDF",
      detail: "Checking document status…",
      percent: 15,
      documentId: params.documentId,
    });
    doc = await getDocument(params.documentId, params.signal);
  } else if (params.file) {
    doc = await uploadOrReusePdf({
      file: params.file,
      examConfigId: params.examConfigId,
      onProgress: params.onProgress,
      signal: params.signal,
    });
  } else {
    throw new Error("Select a PDF file or an existing document first.");
  }

  if (!EXTRACTED_STATUSES.has(doc.status)) {
    params.onProgress?.({
      stepLabel: "Reading PDF pages",
      detail: "Extracting text, tables, and structure…",
      percent: 22,
      documentId: doc.id,
    });
    const extractJob = await processDocument(doc.id, { mode: "extract_only" });
    await waitForJobCompletion(extractJob.id, {
      basePercent: 22,
      spanPercent: 23,
      stepLabel: "Reading PDF pages",
      documentId: doc.id,
      onProgress: params.onProgress,
      signal: params.signal,
    });
    doc = await getDocument(doc.id, params.signal);
  }

  let topicCount = 0;
  let hasKnowledge = false;
  if (KNOWLEDGE_READY_STATUSES.has(doc.status)) {
    try {
      const k = await getDocumentKnowledge(doc.id, params.signal);
      topicCount = k.topics.length;
      hasKnowledge =
        k.topics.length > 0 || k.concepts.length > 0 || k.facts.length > 0;
    } catch {
      hasKnowledge = false;
    }
  }

  if (!hasKnowledge) {
    params.onProgress?.({
      stepLabel: "Extracting key concepts",
      detail: "Identifying topics, facts, and questions…",
      percent: 48,
      documentId: doc.id,
    });
    const knowledgeJob = await extractKnowledge(doc.id, false);
    await waitForJobCompletion(knowledgeJob.id, {
      basePercent: 48,
      spanPercent: 27,
      stepLabel: "Extracting key concepts",
      documentId: doc.id,
      onProgress: params.onProgress,
      signal: params.signal,
    });
    const k = await getDocumentKnowledge(doc.id, params.signal);
    topicCount = k.topics.length;
    doc = await getDocument(doc.id, params.signal);
  }

  return { document: doc, topicCount };
}

/**
 * 1-step PDF -> Smart Notes pipeline (upload -> extract -> knowledge -> notes).
 */
export async function runPdfToNotesPipeline(params: {
  file?: File | null;
  documentId?: string;
  examConfigId?: string | null;
  onProgress?: ProgressCallback;
  signal?: AbortSignal;
}): Promise<{
  document: DocumentItem;
  notes: NoteSummaryOut[];
}> {
  const { document: doc, topicCount } = await ensureDocumentKnowledgeReady({
    file: params.file,
    documentId: params.documentId,
    examConfigId: params.examConfigId,
    onProgress: params.onProgress,
    signal: params.signal,
  });

  const existingNotesRes = await listDocumentNotes(
    doc.id,
    { limit: 100 },
    params.signal,
  );
  if (existingNotesRes.items.length > 0 && params.documentId) {
    // Re-running on an existing doc from a quick flow shouldn't duplicate work unless forced;
    // return ready notes immediately if already generated for quick access.
    return { document: doc, notes: existingNotesRes.items };
  }

  const isMultiTopic = topicCount > 8;
  const noteTypes: NoteType[] = isMultiTopic
    ? ["quick_revision"]
    : ["detailed", "quick_revision", "formula_sheet", "strategy_sheet"];

  params.onProgress?.({
    stepLabel: "Generating Smart Notes",
    detail: isMultiTopic
      ? "Writing quick-revision notes for top topics…"
      : "Writing detailed notes, revision sheets & formulas…",
    percent: 78,
    documentId: doc.id,
  });

  const notesJob = await generateDocumentNotes(doc.id, {
    note_types: noteTypes,
    max_topics: isMultiTopic ? 8 : null,
    force_regenerate: false,
  });

  await waitForJobCompletion(notesJob.id, {
    basePercent: 78,
    spanPercent: 20,
    stepLabel: "Generating Smart Notes",
    documentId: doc.id,
    onProgress: params.onProgress,
    signal: params.signal,
  });

  const notesRes = await listDocumentNotes(doc.id, { limit: 100 }, params.signal);
  params.onProgress?.({
    stepLabel: "Notes Ready",
    detail: `${notesRes.items.length} study notes generated`,
    percent: 100,
    documentId: doc.id,
  });

  return { document: doc, notes: notesRes.items };
}

/**
 * 1-step PDF -> Practice Questions pipeline (extracts/generates MCQs into Question Bank).
 */
export async function runPdfToQuestionsPipeline(params: {
  file?: File | null;
  documentId?: string;
  examConfigId?: string | null;
  desiredCount?: number;
  onProgress?: ProgressCallback;
  signal?: AbortSignal;
}): Promise<{ document: DocumentItem; questionCount: number }> {
  const targetCount = params.desiredCount ?? 10;
  const { document: doc } = await ensureDocumentKnowledgeReady({
    file: params.file,
    documentId: params.documentId,
    examConfigId: params.examConfigId,
    onProgress: params.onProgress,
    signal: params.signal,
  });

  const existing = await listDocumentQuestions(
    doc.id,
    { limit: 100 },
    params.signal,
  );
  let totalCount = existing.total;

  if (totalCount < targetCount) {
    const needed = Math.min(20, Math.max(5, targetCount - totalCount));
    params.onProgress?.({
      stepLabel: "Generating practice questions",
      detail: `Creating ${needed} source-grounded MCQs…`,
      percent: 84,
      documentId: doc.id,
    });
    const genRes = await generateQuestions({
      document_id: doc.id,
      count: needed,
    });
    totalCount += genRes.created.length;
  }

  params.onProgress?.({
    stepLabel: "Questions Ready",
    detail: `${totalCount} questions available`,
    percent: 100,
    documentId: doc.id,
  });

  return { document: doc, questionCount: totalCount };
}

/**
 * 1-step PDF -> Timed Test Attempt pipeline (prepares questions, creates test, starts attempt).
 */
export async function runPdfToTestAttemptPipeline(params: {
  file?: File | null;
  documentId?: string;
  examConfigId?: string | null;
  timerMode?: TimerMode;
  questionCount?: number;
  perQuestionSeconds?: number;
  onProgress?: ProgressCallback;
  signal?: AbortSignal;
}): Promise<{ attemptId: string; document: DocumentItem }> {
  const qCount = params.questionCount ?? 10;
  const timerMode = params.timerMode ?? "speed_challenge";

  const { document: doc, questionCount: availableCount } =
    await runPdfToQuestionsPipeline({
      file: params.file,
      documentId: params.documentId,
      examConfigId: params.examConfigId,
      desiredCount: qCount,
      onProgress: params.onProgress,
      signal: params.signal,
    });

  if (availableCount === 0) {
    throw new Error("Could not extract or generate practice questions from this PDF.");
  }

  const finalCount = Math.min(qCount, availableCount);
  params.onProgress?.({
    stepLabel: "Launching Practice Test",
    detail: `Preparing ${finalCount}-question mock…`,
    percent: 94,
    documentId: doc.id,
  });

  const test = await createTest({
    title: `${doc.title} — Quick Mock`,
    exam_config_id: doc.exam_config_id ?? params.examConfigId ?? null,
    document_ids: [doc.id],
    origin_mode: "mixed",
    question_count: finalCount,
    timer_mode: timerMode,
    per_question_seconds:
      timerMode === "speed_challenge" ? (params.perQuestionSeconds ?? 35) : 35,
    total_duration_seconds:
      timerMode === "exam_simulation" ? Math.max(300, finalCount * 60) : undefined,
    auto_advance_on_timeout: true,
    points_per_question: 2,
    negative_marking_enabled: true,
    negative_points: 0.5,
    shuffle_questions: false,
    shuffle_options: false,
    show_explanation_after:
      timerMode === "learning_mode" ? "after_question" : "after_submission",
    include_needs_review: true,
  });

  const attempt = await startTestAttempt(test.id);
  return { attemptId: attempt.attempt_id, document: doc };
}
