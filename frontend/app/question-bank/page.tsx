"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ClipboardCheck,
  FileQuestion,
  Sparkles,
  Upload,
} from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { GenerateQuestionsDialog } from "@/components/questions/GenerateQuestionsDialog";
import { ImportQuestionsDialog } from "@/components/questions/ImportQuestionsDialog";
import { QuestionCard } from "@/components/questions/QuestionCard";
import { QuestionDetailDrawer } from "@/components/questions/QuestionDetailDrawer";
import {
  QuestionFilters,
  type QuestionFilterState,
} from "@/components/questions/QuestionFilters";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { listDocuments, type DocumentItem } from "@/lib/api/documents";
import {
  listAllTopics,
  listSubjects,
  type SubjectOut,
  type TopicSummaryOut,
} from "@/lib/api/knowledge";
import { listQuestions, type QuestionOut } from "@/lib/api/questions";

function QuestionBankContent() {
  const searchParams = useSearchParams();
  const initialDocId = searchParams.get("document_id") ?? "";

  const [filters, setFilters] = React.useState<QuestionFilterState>({
    q: "",
    subject_code: "",
    topic_id: "",
    difficulty: "",
    origin: "",
    validation_status: "",
    document_id: initialDocId,
  });

  const [questions, setQuestions] = React.useState<QuestionOut[]>([]);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const [subjects, setSubjects] = React.useState<SubjectOut[]>([]);
  const [topics, setTopics] = React.useState<TopicSummaryOut[]>([]);
  const [documents, setDocuments] = React.useState<DocumentItem[]>([]);

  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [inspectId, setInspectId] = React.useState<string | null>(null);
  const [generateOpen, setGenerateOpen] = React.useState(false);
  const [importOpen, setImportOpen] = React.useState(false);

  React.useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      listSubjects(controller.signal).catch(() => [] as SubjectOut[]),
      listAllTopics(undefined, controller.signal)
        .then((r) => r.items)
        .catch(() => [] as TopicSummaryOut[]),
      listDocuments({ limit: 100 }, controller.signal)
        .then((r) => r.items)
        .catch(() => [] as DocumentItem[]),
    ]).then(([subs, tops, docs]) => {
      setSubjects(subs);
      setTopics(tops);
      setDocuments(docs);
    });
    return () => controller.abort();
  }, []);

  const fetchQuestions = React.useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const res = await listQuestions(
          {
            q: filters.q || undefined,
            subject_code: filters.subject_code || undefined,
            topic_id: filters.topic_id || undefined,
            difficulty: filters.difficulty || undefined,
            origin: filters.origin || undefined,
            validation_status: filters.validation_status || undefined,
            document_id: filters.document_id || undefined,
            limit: 50,
            offset: 0,
          },
          signal,
        );
        setQuestions(res.items);
        setTotal(res.total);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load question bank.",
        );
      } finally {
        setIsLoading(false);
      }
    },
    [filters],
  );

  React.useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void fetchQuestions(controller.signal);
    }, 150);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [fetchQuestions]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const buildTestHref = React.useMemo(() => {
    const params = new URLSearchParams();
    if (selectedIds.length > 0) {
      params.set("question_ids", selectedIds.join(","));
    } else {
      if (filters.document_id) params.set("document_id", filters.document_id);
      if (filters.subject_code) params.set("subject_code", filters.subject_code);
      if (filters.topic_id) params.set("topic_id", filters.topic_id);
    }
    const qs = params.toString();
    return `/tests/new${qs ? `?${qs}` : ""}`;
  }, [selectedIds, filters.document_id, filters.subject_code, filters.topic_id]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Question Bank"
        description="Browse, filter, validate, and review extracted, generated, and imported questions."
        actions={
          <>
            <Button
              type="button"
              size="sm"
              onClick={() => setGenerateOpen(true)}
            >
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              <span>Generate Questions</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setImportOpen(true)}
            >
              <Upload className="h-4 w-4" aria-hidden="true" />
              <span>Import PYQs</span>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href={buildTestHref}>
                <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
                <span>
                  {selectedIds.length > 0
                    ? `Create Test (${selectedIds.length} selected)`
                    : "Create Test"}
                </span>
              </Link>
            </Button>
          </>
        }
      />

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Questions</CardTitle>
              <CardDescription>
                {isLoading
                  ? "Loading question bank…"
                  : `${total} ${total === 1 ? "question" : "questions"} matching filters`}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {selectedIds.length > 0 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedIds([])}
                >
                  Clear selection ({selectedIds.length})
                </Button>
              ) : null}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void fetchQuestions()}
                disabled={isLoading}
              >
                Refresh
              </Button>
            </div>
          </div>

          <div className="mt-2">
            <QuestionFilters
              filters={filters}
              onChange={setFilters}
              subjects={subjects}
              topics={topics}
              documents={documents}
            />
          </div>
        </CardHeader>

        <CardContent>
          {errorMessage ? (
            <div
              role="alert"
              className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
            >
              {errorMessage}
            </div>
          ) : isLoading && questions.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              Loading questions…
            </p>
          ) : questions.length === 0 ? (
            <div className="rounded-md border border-dashed px-4 py-10 text-center">
              <FileQuestion
                className="mx-auto h-8 w-8 text-muted-foreground"
                aria-hidden="true"
              />
              <p className="mt-2 text-sm font-medium">No questions found</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Import previous-year questions (JSON or CSV), generate AI
                questions from an extracted document, or upload a study PDF.
              </p>
              <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => setImportOpen(true)}
                >
                  <Upload className="h-4 w-4" aria-hidden="true" />
                  <span>Import PYQs</span>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setGenerateOpen(true)}
                >
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  <span>Generate Questions</span>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link href="/library">Upload PDF</Link>
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {questions.map((question) => (
                <QuestionCard
                  key={question.id}
                  question={question}
                  selected={selectedIds.includes(question.id)}
                  onToggleSelect={toggleSelect}
                  onInspect={(id) => setInspectId(id)}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <QuestionDetailDrawer
        questionId={inspectId}
        onClose={() => setInspectId(null)}
        onQuestionUpdated={(updated) => {
          setQuestions((prev) =>
            prev.map((q) => (q.id === updated.id ? updated : q)),
          );
        }}
        onQuestionDeleted={(deletedId) => {
          setQuestions((prev) => prev.filter((q) => q.id !== deletedId));
          setTotal((prev) => Math.max(0, prev - 1));
          setSelectedIds((prev) => prev.filter((id) => id !== deletedId));
        }}
      />

      <GenerateQuestionsDialog
        open={generateOpen}
        defaultDocumentId={filters.document_id}
        documents={documents}
        subjects={subjects}
        topics={topics}
        onClose={() => setGenerateOpen(false)}
        onGenerated={() => void fetchQuestions()}
      />

      <ImportQuestionsDialog
        open={importOpen}
        subjects={subjects}
        onClose={() => setImportOpen(false)}
        onImported={() => void fetchQuestions()}
      />
    </div>
  );
}

export default function QuestionBankPage() {
  return (
    <React.Suspense
      fallback={
        <div className="py-10 text-center text-sm text-muted-foreground">
          Loading question bank…
        </div>
      }
    >
      <QuestionBankContent />
    </React.Suspense>
  );
}
