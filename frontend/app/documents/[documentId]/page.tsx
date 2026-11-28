"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ExternalLink,
  FileQuestion,
  FileText,
  Play,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";

import { CoverageReportCard } from "@/components/documents/CoverageReportCard";
import {
  DocumentMetadataFields,
  type MetadataFormValues,
} from "@/components/documents/DocumentMetadataFields";
import { KnowledgePanel } from "@/components/documents/KnowledgePanel";
import { PageReviewList } from "@/components/documents/PageReviewList";
import { ProcessingStages } from "@/components/documents/ProcessingStages";
import { PyqPatternsCard } from "@/components/documents/PyqPatternsCard";
import { GenerateQuestionsDialog } from "@/components/questions/GenerateQuestionsDialog";
import { QuestionCard } from "@/components/questions/QuestionCard";
import { QuestionDetailDrawer } from "@/components/questions/QuestionDetailDrawer";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  deleteDocument,
  formatBytes,
  getDocument,
  getDocumentCoverage,
  getDocumentPages,
  updateDocumentMetadata,
  type CoverageAuditOut,
  type DocumentItem,
  type DocumentPageOut,
} from "@/lib/api/documents";
import {
  formatSubjectLabel,
  listExamConfigs,
  type ExamConfig,
} from "@/lib/api/examConfigs";
import {
  listJobs,
  processDocument,
  retryJob,
  type ProcessingJobOut,
} from "@/lib/api/jobs";
import {
  extractKnowledge,
  getDocumentKnowledge,
  listSubjects,
  overrideDocumentClassification,
  updateFact,
  type DocumentKnowledgeOut,
  type SubjectOut,
} from "@/lib/api/knowledge";
import {
  formatNoteType,
  generateDocumentNotes,
  getDocumentPyqPatterns,
  listDocumentNotes,
  type NoteSummaryOut,
  type NoteType,
  type PyqPatternsOut,
} from "@/lib/api/notes";
import {
  listDocumentQuestions,
  type QuestionOut,
} from "@/lib/api/questions";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { cn } from "@/lib/utils/cn";

type WorkspaceTab =
  | "overview"
  | "source_pages"
  | "knowledge"
  | "detailed_notes"
  | "quick_revision"
  | "strategies"
  | "questions";

const WORKSPACE_TABS: readonly {
  id: WorkspaceTab;
  label: string;
  milestone?: string;
}[] = [
  { id: "overview", label: "Overview" },
  { id: "source_pages", label: "Source Pages" },
  { id: "knowledge", label: "Knowledge" },
  { id: "detailed_notes", label: "Detailed Notes" },
  { id: "quick_revision", label: "Quick Revision" },
  { id: "strategies", label: "Formulas / Shortcuts" },
  { id: "questions", label: "Questions" },
] as const;

function toMetadataValues(doc: DocumentItem): MetadataFormValues {
  return {
    title: doc.title,
    exam_config_id: doc.exam_config_id ?? "",
    subject_code: doc.subject_code ?? "",
    material_type: doc.material_type,
    language: doc.language,
    chapter_or_topic_hint: doc.chapter_or_topic_hint ?? "",
    source_label: doc.source_label ?? "",
  };
}

function DocumentNotesTabPanel({
  title,
  description,
  notes,
  isLoading,
  errorMessage,
  hasKnowledge,
  isGenerating,
  isJobPolling,
  onGenerate,
}: {
  title: string;
  description: string;
  notes: readonly NoteSummaryOut[];
  isLoading: boolean;
  errorMessage: string | null;
  hasKnowledge: boolean;
  isGenerating: boolean;
  isJobPolling: boolean;
  onGenerate: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
        <Button
          type="button"
          size="sm"
          disabled={!hasKnowledge || isGenerating || isJobPolling}
          onClick={onGenerate}
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          <span>
            {isGenerating
              ? "Starting…"
              : isJobPolling
                ? "Generating…"
                : notes.length > 0
                  ? "Regenerate All"
                  : "Generate Notes"}
          </span>
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {!hasKnowledge ? (
          <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            Extract structured knowledge in the <strong>Knowledge</strong> tab
            before generating notes.
          </p>
        ) : null}

        {errorMessage ? (
          <div
            role="alert"
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
          >
            {errorMessage}
          </div>
        ) : isLoading && notes.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Loading notes…
          </p>
        ) : notes.length === 0 ? (
          <div className="rounded-md border border-dashed py-8 text-center">
            <BookOpen
              className="mx-auto h-7 w-7 text-muted-foreground"
              aria-hidden="true"
            />
            <p className="mt-2 text-sm font-medium">No notes generated yet</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Click Generate Notes above to create topic-wise study notes from
              validated knowledge records.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {notes.map((note) => (
              <div
                key={note.id}
                className="flex flex-col justify-between rounded-md border p-4"
              >
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant="secondary">
                      {formatNoteType(note.note_type)}
                    </Badge>
                    {note.subject_code ? (
                      <Badge variant="outline">
                        {formatSubjectLabel(note.subject_code)}
                      </Badge>
                    ) : null}
                    {note.understood_at ? (
                      <Badge variant="success">Understood</Badge>
                    ) : null}
                  </div>
                  <h4 className="font-semibold">{note.title}</h4>
                  <p className="text-xs text-muted-foreground">
                    {note.topic_name ? `${note.topic_name} · ` : ""}v
                    {note.generation_version} · {note.status.replace(/_/g, " ")}
                  </p>
                </div>
                <div className="mt-3">
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/notes/${encodeURIComponent(note.id)}`}>
                      <span>Open Reader</span>
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    </Link>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function DocumentWorkspacePage() {
  const params = useParams<{ documentId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const documentId = params.documentId;

  const initialTabParam = searchParams.get("tab");
  const initialTab: WorkspaceTab = WORKSPACE_TABS.some(
    (t) => t.id === initialTabParam,
  )
    ? (initialTabParam as WorkspaceTab)
    : "overview";

  const [activeTab, setActiveTab] = React.useState<WorkspaceTab>(initialTab);
  const [doc, setDoc] = React.useState<DocumentItem | null>(null);
  const [examConfigs, setExamConfigs] = React.useState<ExamConfig[]>([]);
  const [subjects, setSubjects] = React.useState<SubjectOut[]>([]);
  const [metadata, setMetadata] = React.useState<MetadataFormValues | null>(
    null,
  );
  const [isLoading, setIsLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const [coverage, setCoverage] = React.useState<CoverageAuditOut | null>(null);
  const [coverageLoading, setCoverageLoading] = React.useState(false);
  const [coverageError, setCoverageError] = React.useState<string | null>(null);

  const [pages, setPages] = React.useState<DocumentPageOut[]>([]);
  const [pagesLoading, setPagesLoading] = React.useState(false);
  const [pagesError, setPagesError] = React.useState<string | null>(null);
  const [needsOcrOnly, setNeedsOcrOnly] = React.useState(false);

  const [knowledge, setKnowledge] = React.useState<DocumentKnowledgeOut | null>(
    null,
  );
  const [knowledgeLoading, setKnowledgeLoading] = React.useState(false);
  const [knowledgeError, setKnowledgeError] = React.useState<string | null>(
    null,
  );
  const [isStartingExtract, setIsStartingExtract] = React.useState(false);

  const [docNotes, setDocNotes] = React.useState<NoteSummaryOut[]>([]);
  const [notesLoading, setNotesLoading] = React.useState(false);
  const [notesError, setNotesError] = React.useState<string | null>(null);
  const [isGeneratingNotes, setIsGeneratingNotes] = React.useState(false);

  const [pyqPatterns, setPyqPatterns] = React.useState<PyqPatternsOut | null>(
    null,
  );
  const [pyqLoading, setPyqLoading] = React.useState(false);
  const [pyqError, setPyqError] = React.useState<string | null>(null);

  const [docQuestions, setDocQuestions] = React.useState<QuestionOut[]>([]);
  const [questionsLoading, setQuestionsLoading] = React.useState(false);
  const [questionsError, setQuestionsError] = React.useState<string | null>(
    null,
  );
  const [selectedQuestionIds, setSelectedQuestionIds] = React.useState<
    string[]
  >([]);
  const [inspectQuestionId, setInspectQuestionId] = React.useState<
    string | null
  >(null);
  const [generateQuestionsOpen, setGenerateQuestionsOpen] =
    React.useState(false);

  const [initialJob, setInitialJob] = React.useState<ProcessingJobOut | null>(
    null,
  );
  const [isStartingProcess, setIsStartingProcess] = React.useState(false);
  const [isRetryingJob, setIsRetryingJob] = React.useState(false);
  const [processError, setProcessError] = React.useState<string | null>(null);

  const [isSaving, setIsSaving] = React.useState(false);
  const [saveSuccess, setSaveSuccess] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [isDeleting, setIsDeleting] = React.useState(false);

  const loadNotesAndPatterns = React.useCallback(
    async (docId: string, signal?: AbortSignal) => {
      setNotesLoading(true);
      setPyqLoading(true);
      setNotesError(null);
      setPyqError(null);

      const [notesRes, pyqRes] = await Promise.allSettled([
        listDocumentNotes(docId, { limit: 100 }, signal),
        getDocumentPyqPatterns(docId, signal),
      ]);

      if (notesRes.status === "fulfilled") {
        setDocNotes(notesRes.value.items);
      } else if (
        !(
          notesRes.reason instanceof DOMException &&
          notesRes.reason.name === "AbortError"
        )
      ) {
        setNotesError(
          notesRes.reason instanceof Error
            ? notesRes.reason.message
            : "Failed to load notes.",
        );
      }
      setNotesLoading(false);

      if (pyqRes.status === "fulfilled") {
        setPyqPatterns(pyqRes.value);
      } else if (
        !(
          pyqRes.reason instanceof DOMException &&
          pyqRes.reason.name === "AbortError"
        )
      ) {
        setPyqError(
          pyqRes.reason instanceof Error
            ? pyqRes.reason.message
            : "Failed to load PYQ patterns.",
        );
      }
      setPyqLoading(false);
    },
    [],
  );

  const loadDocQuestions = React.useCallback(
    async (docId: string, signal?: AbortSignal) => {
      setQuestionsLoading(true);
      setQuestionsError(null);
      try {
        const res = await listDocumentQuestions(docId, { limit: 100 }, signal);
        setDocQuestions(res.items);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setQuestionsError(
          error instanceof Error
            ? error.message
            : "Failed to load document questions.",
        );
      } finally {
        setQuestionsLoading(false);
      }
    },
    [],
  );

  const loadKnowledge = React.useCallback(
    async (docId: string, signal?: AbortSignal) => {
      setKnowledgeLoading(true);
      setKnowledgeError(null);
      try {
        const res = await getDocumentKnowledge(docId, signal);
        setKnowledge(res);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setKnowledgeError(
          error instanceof Error
            ? error.message
            : "Failed to load extracted knowledge.",
        );
      } finally {
        setKnowledgeLoading(false);
      }
    },
    [],
  );

  const loadCoverageAndPages = React.useCallback(
    async (docId: string, ocrOnly: boolean, signal?: AbortSignal) => {
      setCoverageLoading(true);
      setPagesLoading(true);
      setCoverageError(null);
      setPagesError(null);

      const [covResult, pagesResult] = await Promise.allSettled([
        getDocumentCoverage(docId, signal),
        getDocumentPages(docId, ocrOnly, signal),
      ]);

      if (covResult.status === "fulfilled") {
        setCoverage(covResult.value);
      } else if (
        !(
          covResult.reason instanceof DOMException &&
          covResult.reason.name === "AbortError"
        )
      ) {
        setCoverageError(
          covResult.reason instanceof Error
            ? covResult.reason.message
            : "Failed to load coverage audit.",
        );
      }
      setCoverageLoading(false);

      if (pagesResult.status === "fulfilled") {
        setPages(pagesResult.value.items);
      } else if (
        !(
          pagesResult.reason instanceof DOMException &&
          pagesResult.reason.name === "AbortError"
        )
      ) {
        setPagesError(
          pagesResult.reason instanceof Error
            ? pagesResult.reason.message
            : "Failed to load extracted pages.",
        );
      }
      setPagesLoading(false);
    },
    [],
  );

  const {
    job: activeJob,
    setJob: setActiveJob,
    isPolling,
    pollError,
  } = useJobPolling({
    initialJob,
    onTerminal: () => {
      if (!documentId) return;
      void getDocument(documentId)
        .then((fresh) => {
          setDoc(fresh);
          setMetadata(toMetadataValues(fresh));
        })
        .catch(() => undefined);
      void loadCoverageAndPages(documentId, needsOcrOnly);
      void loadKnowledge(documentId);
      void loadNotesAndPatterns(documentId);
      void loadDocQuestions(documentId);
    },
  });

  React.useEffect(() => {
    if (!documentId) return;
    const controller = new AbortController();
    setIsLoading(true);
    setLoadError(null);

    Promise.all([
      getDocument(documentId, controller.signal),
      listExamConfigs(controller.signal).catch(() => [] as ExamConfig[]),
      listSubjects(controller.signal).catch(() => [] as SubjectOut[]),
      listJobs({ document_id: documentId }, controller.signal).catch(
        () => [] as ProcessingJobOut[],
      ),
    ])
      .then(([loadedDoc, configs, loadedSubjects, jobs]) => {
        setDoc(loadedDoc);
        setMetadata(toMetadataValues(loadedDoc));
        setExamConfigs(configs);
        setSubjects(loadedSubjects);
        if (jobs.length > 0 && jobs[0]) {
          setInitialJob(jobs[0]);
        }
        void loadCoverageAndPages(documentId, false, controller.signal);
        void loadKnowledge(documentId, controller.signal);
        void loadNotesAndPatterns(documentId, controller.signal);
        void loadDocQuestions(documentId, controller.signal);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setLoadError(
          error instanceof Error ? error.message : "Failed to load document.",
        );
      })
      .finally(() => setIsLoading(false));

    return () => controller.abort();
  }, [
    documentId,
    loadCoverageAndPages,
    loadDocQuestions,
    loadKnowledge,
    loadNotesAndPatterns,
  ]);

  const handleNeedsOcrToggle = (next: boolean) => {
    setNeedsOcrOnly(next);
    if (!documentId) return;
    setPagesLoading(true);
    setPagesError(null);
    getDocumentPages(documentId, next)
      .then((res) => setPages(res.items))
      .catch((error) =>
        setPagesError(
          error instanceof Error
            ? error.message
            : "Failed to filter source pages.",
        ),
      )
      .finally(() => setPagesLoading(false));
  };

  const handleStartProcess = async (forceReextract = false) => {
    if (!doc) return;
    setIsStartingProcess(true);
    setProcessError(null);
    try {
      const createdJob = await processDocument(doc.id, {
        mode: "extract_only",
        force_reextract: forceReextract,
      });
      setActiveJob(createdJob);
    } catch (error) {
      setProcessError(
        error instanceof Error
          ? error.message
          : "Failed to start document processing.",
      );
    } finally {
      setIsStartingProcess(false);
    }
  };

  const handleStartKnowledgeExtract = async (forceReprocess: boolean) => {
    if (!doc) return;
    setIsStartingExtract(true);
    setProcessError(null);
    setKnowledgeError(null);
    try {
      const createdJob = await extractKnowledge(doc.id, forceReprocess);
      setActiveJob(createdJob);
    } catch (error) {
      setKnowledgeError(
        error instanceof Error
          ? error.message
          : "Failed to start knowledge extraction.",
      );
    } finally {
      setIsStartingExtract(false);
    }
  };

  const handleGenerateNotes = async (
    noteTypes: NoteType[],
    options?: { maxTopics?: number; forceRegenerate?: boolean },
  ) => {
    if (!doc) return;
    setIsGeneratingNotes(true);
    setNotesError(null);
    setProcessError(null);
    try {
      const hasExistingTargetType = noteTypes.some((nt) =>
        docNotes.some((n) => n.note_type === nt),
      );
      const createdJob = await generateDocumentNotes(doc.id, {
        note_types: noteTypes,
        max_topics: options?.maxTopics ?? null,
        force_regenerate: options?.forceRegenerate ?? hasExistingTargetType,
      });
      setActiveJob(createdJob);
    } catch (error) {
      setNotesError(
        error instanceof Error
          ? error.message
          : "Failed to start notes generation.",
      );
    } finally {
      setIsGeneratingNotes(false);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    setIsRetryingJob(true);
    setProcessError(null);
    try {
      const retried = await retryJob(jobId);
      setActiveJob(retried);
    } catch (error) {
      setProcessError(
        error instanceof Error ? error.message : "Failed to retry job.",
      );
    } finally {
      setIsRetryingJob(false);
    }
  };

  const handleOverrideClassification = async (payload: {
    subject_code: string | null;
    material_type: string;
    language: string;
  }) => {
    if (!doc) return;
    setKnowledgeError(null);
    try {
      const updated = await overrideDocumentClassification(doc.id, payload);
      setDoc(updated);
      setMetadata(toMetadataValues(updated));
      await loadKnowledge(doc.id);
    } catch (error) {
      setKnowledgeError(
        error instanceof Error
          ? error.message
          : "Failed to override classification.",
      );
    }
  };

  const handleUpdateFact = async (
    factId: string,
    payload: { content?: string; review_status?: string },
  ) => {
    if (!doc) return;
    setKnowledgeError(null);
    try {
      const updatedFact = await updateFact(factId, payload);
      setKnowledge((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          facts: prev.facts.map((f) => (f.id === factId ? updatedFact : f)),
        };
      });
    } catch (error) {
      setKnowledgeError(
        error instanceof Error ? error.message : "Failed to update fact.",
      );
    }
  };

  const handleSaveMetadata = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!doc || !metadata) return;

    const trimmedTitle = metadata.title.trim();
    if (!trimmedTitle) {
      setSaveError("Title cannot be empty.");
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      const updated = await updateDocumentMetadata(doc.id, {
        title: trimmedTitle,
        exam_config_id: metadata.exam_config_id || null,
        subject_code: metadata.subject_code || null,
        material_type: metadata.material_type,
        language: metadata.language,
        chapter_or_topic_hint: metadata.chapter_or_topic_hint.trim() || null,
        source_label: metadata.source_label.trim() || null,
      });
      setDoc(updated);
      setMetadata(toMetadataValues(updated));
      setSaveSuccess(true);
    } catch (error) {
      setSaveError(
        error instanceof Error
          ? error.message
          : "Failed to update document metadata.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteDocument = async () => {
    if (!doc) return;
    setIsDeleting(true);
    setSaveError(null);
    try {
      await deleteDocument(doc.id, true);
      router.push("/library");
    } catch (error) {
      setSaveError(
        error instanceof Error ? error.message : "Failed to delete document.",
      );
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Document Workspace"
          description="Loading document workspace…"
          actions={
            <Button asChild variant="outline" size="sm">
              <Link href="/library">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>Back to Library</span>
              </Link>
            </Button>
          }
        />
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Loading document record…
          </CardContent>
        </Card>
      </div>
    );
  }

  if (loadError || !doc || !metadata) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Document Unavailable"
          description="Unable to retrieve this document from the backend."
          actions={
            <Button asChild variant="outline" size="sm">
              <Link href="/library">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>Back to Library</span>
              </Link>
            </Button>
          }
        />
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{loadError ?? "Document not found."}</span>
        </div>
      </div>
    );
  }

  const alreadyExtracted = pages.length > 0 || (coverage?.chunks_created ?? 0) > 0;
  const hasKnowledge =
    (knowledge?.topics.length ?? 0) > 0 ||
    (knowledge?.concepts.length ?? 0) > 0 ||
    (knowledge?.facts.length ?? 0) > 0;

  const topicCount = knowledge?.topics.length ?? 0;
  const isMultiTopicDoc = topicCount > 8;
  const detailedNotes = docNotes.filter((n) => n.note_type === "detailed");
  const quickRevisionNotes = docNotes.filter(
    (n) => n.note_type === "quick_revision",
  );
  const strategyNotes = docNotes.filter(
    (n) => n.note_type === "formula_sheet" || n.note_type === "strategy_sheet",
  );
  const tabCounts: Partial<Record<WorkspaceTab, number>> = {
    source_pages: pages.length,
    knowledge:
      topicCount +
      (knowledge?.concepts.length ?? 0) +
      (knowledge?.facts.length ?? 0),
    detailed_notes: detailedNotes.length,
    quick_revision: quickRevisionNotes.length,
    strategies: strategyNotes.length,
    questions: docQuestions.length,
  };

  const hasNotes = docNotes.length > 0;
  const hasQuestions = docQuestions.length > 0;
  const isPipelineBusy =
    isPolling || isStartingProcess || isStartingExtract || isGeneratingNotes;

  const pipelineSteps: Array<{
    step: number;
    label: string;
    detail: string;
    done: boolean;
    active: boolean;
    tab: WorkspaceTab;
  }> = [
    {
      step: 1,
      label: "Extract Pages",
      detail: alreadyExtracted
        ? `${pages.length} ${pages.length === 1 ? "page" : "pages"} extracted`
        : "Read text, tables & diagrams",
      done: alreadyExtracted,
      active: !alreadyExtracted,
      tab: "source_pages",
    },
    {
      step: 2,
      label: "AI Knowledge & Questions",
      detail: hasKnowledge
        ? `${knowledge?.concepts.length ?? 0} concepts · ${knowledge?.facts.length ?? 0} facts`
        : "Extract topics, rules & PYQs",
      done: hasKnowledge,
      active: alreadyExtracted && !hasKnowledge,
      tab: "knowledge",
    },
    {
      step: 3,
      label: "Generate Study Notes",
      detail: hasNotes
        ? `${docNotes.length} ${docNotes.length === 1 ? "note" : "notes"} ready`
        : "Detailed, quick revision & formulas",
      done: hasNotes,
      active: alreadyExtracted && hasKnowledge && !hasNotes,
      tab: "detailed_notes",
    },
    {
      step: 4,
      label: "Practice Test",
      detail: hasQuestions
        ? `${docQuestions.length} ${docQuestions.length === 1 ? "question" : "questions"} ready`
        : "Build or generate timed practice",
      done: hasQuestions,
      active: alreadyExtracted && hasKnowledge && hasNotes,
      tab: "questions",
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={doc.title}
        description={`${doc.original_filename} · Uploaded ${new Date(doc.created_at).toLocaleString()}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="capitalize">
              {doc.status.replace(/_/g, " ")}
            </Badge>
            <Button
              type="button"
              size="sm"
              variant={alreadyExtracted ? "outline" : "default"}
              disabled={isStartingProcess || isPolling}
              onClick={() => void handleStartProcess(alreadyExtracted)}
            >
              {alreadyExtracted ? (
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Play className="h-4 w-4" aria-hidden="true" />
              )}
              <span>
                {isStartingProcess
                  ? "Starting…"
                  : isPolling
                    ? "Processing…"
                    : alreadyExtracted
                      ? "Re-extract Pages"
                      : "Extract Pages"}
              </span>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/library">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>Back to Library</span>
              </Link>
            </Button>
          </div>
        }
      />

      {processError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{processError}</span>
        </div>
      ) : null}

      {activeJob ? (
        <ProcessingStages
          job={activeJob}
          isPolling={isPolling}
          pollError={pollError}
          isRetrying={isRetryingJob}
          onRetry={(id) => void handleRetryJob(id)}
        />
      ) : null}

      {/* 4-Step Document Study Guide / Pipeline Progress Bar */}
      <Card className="border-primary/20 bg-primary/[0.02]">
        <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">
              Document Study Guide
            </CardTitle>
            <CardDescription className="text-xs">
              Follow these 4 steps to turn this file into study notes and mock
              tests.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {!alreadyExtracted ? (
              <Button
                type="button"
                size="sm"
                disabled={isPipelineBusy}
                onClick={() => void handleStartProcess(false)}
              >
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Next: Extract Pages</span>
              </Button>
            ) : !hasKnowledge ? (
              <Button
                type="button"
                size="sm"
                disabled={isPipelineBusy}
                onClick={() => void handleStartKnowledgeExtract(false)}
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Next: Extract AI Knowledge &amp; Questions</span>
              </Button>
            ) : !hasNotes ? (
              <Button
                type="button"
                size="sm"
                disabled={isPipelineBusy}
                title={
                  isMultiTopicDoc
                    ? "Generates concise Quick Revision notes for the top 8 topics first"
                    : undefined
                }
                onClick={() =>
                  void handleGenerateNotes(
                    isMultiTopicDoc
                      ? ["quick_revision"]
                      : [
                          "detailed",
                          "quick_revision",
                          "formula_sheet",
                          "strategy_sheet",
                        ],
                    { maxTopics: isMultiTopicDoc ? 8 : undefined },
                  )
                }
              >
                <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Next: Generate Study Notes</span>
              </Button>
            ) : hasQuestions ? (
              <Button asChild size="sm">
                <Link
                  href={`/tests/new?document_id=${encodeURIComponent(doc.id)}`}
                >
                  <Play className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Start Practice Test</span>
                </Link>
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={() => setGenerateQuestionsOpen(true)}
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Next: Generate Practice Questions</span>
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <ol className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {pipelineSteps.map((s) => (
              <li key={s.step}>
                <button
                  type="button"
                  onClick={() => setActiveTab(s.tab)}
                  className={cn(
                    "flex w-full items-start gap-2.5 rounded-md border p-3 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    s.done
                      ? "border-emerald-200 bg-emerald-50/60"
                      : s.active
                        ? "border-primary bg-background shadow-sm ring-1 ring-primary/30"
                        : "bg-background/60",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                      s.done
                        ? "bg-emerald-600 text-white"
                        : s.active
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground",
                    )}
                  >
                    {s.done ? (
                      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                    ) : (
                      s.step
                    )}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-foreground">
                      {s.step}. {s.label}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {s.detail}
                    </p>
                  </div>
                </button>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      {/* Workspace Tabs */}
      <div
        role="tablist"
        aria-label="Document workspace sections"
        className="flex items-center gap-1 overflow-x-auto border-b pb-2 lg:flex-nowrap"
      >
        {WORKSPACE_TABS.map((tab) => {
          const isSelected = activeTab === tab.id;
          const count = tabCounts[tab.id];
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-sm",
                isSelected
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <span>{tab.label}</span>
              {typeof count === "number" && count > 0 ? (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none",
                    isSelected
                      ? "bg-primary-foreground/20 text-primary-foreground"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  {count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {activeTab === "overview" ? (
        <div className="space-y-6">
          <CoverageReportCard
            coverage={coverage}
            isLoading={coverageLoading}
            errorMessage={coverageError}
            onInspectPagesRequiringOcr={() => {
              setActiveTab("source_pages");
              handleNeedsOcrToggle(true);
            }}
          />

          <PyqPatternsCard
            patterns={pyqPatterns}
            isLoading={pyqLoading}
            errorMessage={pyqError}
          />

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
                <CardTitle>Document Details</CardTitle>
              </div>
              <CardDescription>
                File format, page count, and storage size for this upload.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
                <div className="rounded-md border bg-muted/40 p-3">
                  <dt className="text-xs font-medium text-muted-foreground">
                    Format
                  </dt>
                  <dd className="mt-1 font-medium uppercase">
                    {doc.source_type.replace(/_/g, " ")}
                  </dd>
                </div>
                <div className="rounded-md border bg-muted/40 p-3">
                  <dt className="text-xs font-medium text-muted-foreground">
                    Length
                  </dt>
                  <dd className="mt-1 font-medium">
                    {doc.page_count} {doc.page_count === 1 ? "page" : "pages"}
                  </dd>
                </div>
                <div className="rounded-md border bg-muted/40 p-3">
                  <dt className="text-xs font-medium text-muted-foreground">
                    File Size
                  </dt>
                  <dd className="mt-1 font-medium">
                    {formatBytes(doc.file_size_bytes)}
                  </dd>
                </div>
              </dl>

              <details className="rounded-md border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                <summary className="cursor-pointer font-medium hover:text-foreground">
                  Technical diagnostics (checksum &amp; file ID)
                </summary>
                <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <div>
                    <dt className="font-medium">Document ID</dt>
                    <dd className="mt-0.5 break-all font-mono">{doc.id}</dd>
                  </div>
                  <div>
                    <dt className="font-medium">SHA-256 Checksum</dt>
                    <dd className="mt-0.5 break-all font-mono">{doc.sha256}</dd>
                  </div>
                </dl>
              </details>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Document Metadata</CardTitle>
              <CardDescription>
                Correct or refine exam, subject, material type, and chapter
                hints.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveMetadata} className="space-y-4">
                <DocumentMetadataFields
                  values={metadata}
                  onChange={(next) => {
                    setMetadata(next);
                    setSaveSuccess(false);
                  }}
                  examConfigs={examConfigs}
                  titleRequired
                  titlePlaceholder="Document title"
                  disabled={isSaving || isDeleting}
                  idPrefix="edit-doc"
                />

                {saveError ? (
                  <div
                    role="alert"
                    className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
                  >
                    <AlertCircle
                      className="mt-0.5 h-4 w-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span>{saveError}</span>
                  </div>
                ) : null}

                {saveSuccess ? (
                  <div
                    role="status"
                    aria-live="polite"
                    className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"
                  >
                    <CheckCircle2
                      className="h-4 w-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span>Metadata updated.</span>
                  </div>
                ) : null}

                <div className="flex justify-end">
                  <Button type="submit" disabled={isSaving || isDeleting}>
                    {isSaving ? "Saving…" : "Save Changes"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          <Card className="border-red-200">
            <CardHeader>
              <CardTitle className="text-destructive">
                Delete Document
              </CardTitle>
              <CardDescription>
                Removes the private stored file and derived study records for
                this document. Questions already included in historical tests
                remain detached so test history stays intact.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {confirmDelete ? (
                <div className="flex flex-wrap items-center gap-3">
                  <p className="text-sm font-medium text-destructive">
                    Confirm permanent deletion of &ldquo;{doc.title}&rdquo;?
                  </p>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    disabled={isDeleting}
                    onClick={() => void handleDeleteDocument()}
                  >
                    {isDeleting ? "Deleting…" : "Yes, Delete Permanently"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={isDeleting}
                    onClick={() => setConfirmDelete(false)}
                  >
                    Cancel
                  </Button>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={() => setConfirmDelete(true)}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                  <span>Delete Document</span>
                </Button>
              )}
            </CardContent>
          </Card>
        </div>
      ) : activeTab === "source_pages" ? (
        <PageReviewList
          documentId={doc.id}
          pages={pages}
          isLoading={pagesLoading}
          errorMessage={pagesError}
          needsOcrOnly={needsOcrOnly}
          onNeedsOcrOnlyChange={handleNeedsOcrToggle}
          onRefresh={() =>
            void loadCoverageAndPages(doc.id, needsOcrOnly)
          }
        />
      ) : activeTab === "knowledge" ? (
        <KnowledgePanel
          document={doc}
          knowledge={knowledge}
          subjects={subjects}
          isLoading={knowledgeLoading}
          errorMessage={knowledgeError}
          hasExtractedPages={alreadyExtracted}
          isStartingExtract={isStartingExtract}
          isJobPolling={isPolling}
          onExtractKnowledge={(force) => void handleStartKnowledgeExtract(force)}
          onOverrideClassification={handleOverrideClassification}
          onUpdateFact={handleUpdateFact}
          onRefresh={() => void loadKnowledge(doc.id)}
        />
      ) : activeTab === "detailed_notes" ? (
        <DocumentNotesTabPanel
          title="Detailed Smart Notes"
          description="Structured, source-grounded topic explanations with worked examples and citations."
          notes={detailedNotes}
          isLoading={notesLoading}
          errorMessage={notesError}
          hasKnowledge={hasKnowledge}
          isGenerating={isGeneratingNotes}
          isJobPolling={isPolling}
          onGenerate={() =>
            void handleGenerateNotes(["detailed"], {
              maxTopics: isMultiTopicDoc ? 8 : undefined,
            })
          }
        />
      ) : activeTab === "quick_revision" ? (
        <DocumentNotesTabPanel
          title="Quick Revision Notes"
          description="Concise revision sheets, key facts, traps, and 1-minute recaps."
          notes={quickRevisionNotes}
          isLoading={notesLoading}
          errorMessage={notesError}
          hasKnowledge={hasKnowledge}
          isGenerating={isGeneratingNotes}
          isJobPolling={isPolling}
          onGenerate={() =>
            void handleGenerateNotes(["quick_revision"], {
              maxTopics: topicCount > 10 ? 10 : undefined,
            })
          }
        />
      ) : activeTab === "strategies" ? (
        <DocumentNotesTabPanel
          title="Formulas, Rules & Solving Strategies"
          description="Subject-specific solving methods, grammar rules, shortcuts, and limitations."
          notes={strategyNotes}
          isLoading={notesLoading}
          errorMessage={notesError}
          hasKnowledge={hasKnowledge}
          isGenerating={isGeneratingNotes}
          isJobPolling={isPolling}
          onGenerate={() =>
            void handleGenerateNotes(["formula_sheet", "strategy_sheet"], {
              maxTopics: isMultiTopicDoc ? 8 : undefined,
            })
          }
        />
      ) : (
        <Card>
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>Document Questions ({docQuestions.length})</CardTitle>
              <CardDescription>
                Extracted and generated questions linked to this document.
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                disabled={!hasKnowledge}
                onClick={() => setGenerateQuestionsOpen(true)}
              >
                <Sparkles className="h-4 w-4" aria-hidden="true" />
                <span>Generate Questions</span>
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link
                  href={`/question-bank?document_id=${encodeURIComponent(doc.id)}`}
                >
                  <ExternalLink className="h-4 w-4" aria-hidden="true" />
                  <span>Open in Question Bank</span>
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {questionsError ? (
              <div
                role="alert"
                className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
              >
                {questionsError}
              </div>
            ) : questionsLoading && docQuestions.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Loading questions…
              </p>
            ) : docQuestions.length === 0 ? (
              <div className="rounded-md border border-dashed py-8 text-center">
                <FileQuestion
                  className="mx-auto h-7 w-7 text-muted-foreground"
                  aria-hidden="true"
                />
                <p className="mt-2 text-sm font-medium">
                  No questions extracted or generated yet
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Extract knowledge from this document or click Generate
                  Questions above.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {docQuestions.map((question) => (
                  <QuestionCard
                    key={question.id}
                    question={question}
                    selected={selectedQuestionIds.includes(question.id)}
                    onToggleSelect={(id) =>
                      setSelectedQuestionIds((prev) =>
                        prev.includes(id)
                          ? prev.filter((item) => item !== id)
                          : [...prev, id],
                      )
                    }
                    onInspect={(id) => setInspectQuestionId(id)}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <QuestionDetailDrawer
        questionId={inspectQuestionId}
        onClose={() => setInspectQuestionId(null)}
        onQuestionUpdated={(updated) => {
          setDocQuestions((prev) =>
            prev.map((q) => (q.id === updated.id ? updated : q)),
          );
        }}
        onQuestionDeleted={(deletedId) => {
          setDocQuestions((prev) => prev.filter((q) => q.id !== deletedId));
          setSelectedQuestionIds((prev) =>
            prev.filter((id) => id !== deletedId),
          );
        }}
      />

      <GenerateQuestionsDialog
        open={generateQuestionsOpen}
        defaultDocumentId={doc.id}
        subjects={subjects}
        topics={knowledge?.topics ?? []}
        onClose={() => setGenerateQuestionsOpen(false)}
        onGenerated={() => void loadDocQuestions(doc.id)}
      />
    </div>
  );
}
