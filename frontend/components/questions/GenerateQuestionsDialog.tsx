"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { DocumentItem } from "@/lib/api/documents";
import type { SubjectOut, TopicSummaryOut } from "@/lib/api/knowledge";
import {
  generateQuestions,
  type GenerateQuestionsResponse,
} from "@/lib/api/questions";

interface GenerateQuestionsDialogProps {
  open: boolean;
  defaultDocumentId?: string;
  documents?: readonly DocumentItem[];
  subjects: readonly SubjectOut[];
  topics: readonly TopicSummaryOut[];
  onClose: () => void;
  onGenerated: (result: GenerateQuestionsResponse) => void;
}

export function GenerateQuestionsDialog({
  open,
  defaultDocumentId = "",
  documents = [],
  subjects,
  topics,
  onClose,
  onGenerated,
}: GenerateQuestionsDialogProps) {
  const [documentId, setDocumentId] = React.useState(defaultDocumentId);
  const [subjectCode, setSubjectCode] = React.useState("");
  const [topicId, setTopicId] = React.useState("");
  const [difficulty, setDifficulty] = React.useState<
    "easy" | "medium" | "hard" | "mixed"
  >("mixed");
  const [count, setCount] = React.useState(5);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [resultSummary, setResultSummary] =
    React.useState<GenerateQuestionsResponse | null>(null);

  React.useEffect(() => {
    if (open) {
      setDocumentId(defaultDocumentId);
      setErrorMessage(null);
      setResultSummary(null);
    }
  }, [open, defaultDocumentId]);

  if (!open) {
    return null;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    setResultSummary(null);
    try {
      const res = await generateQuestions({
        document_id: documentId || null,
        subject_code: subjectCode || null,
        topic_id: topicId || null,
        difficulty,
        count,
      });
      setResultSummary(res);
      onGenerated(res);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to generate questions.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="gen-q-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-lg rounded-lg border bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="gen-q-title" className="text-lg font-semibold">
              Generate Practice Questions
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Generates MCQs from validated concepts and facts, then runs
              option-uniqueness, deduplication, and deterministic math checks.
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Close dialog"
            disabled={isSubmitting}
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {!defaultDocumentId && documents.length > 0 ? (
            <div>
              <label
                htmlFor="gen-q-doc"
                className="block text-sm font-medium"
              >
                Source Document
              </label>
              <select
                id="gen-q-doc"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                disabled={isSubmitting}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="">Any uploaded document</option>
                {documents.map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    {doc.title}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor="gen-q-subject"
                className="block text-sm font-medium"
              >
                Subject
              </label>
              <select
                id="gen-q-subject"
                value={subjectCode}
                onChange={(e) => setSubjectCode(e.target.value)}
                disabled={isSubmitting}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="">Auto / From Document</option>
                {subjects.map((s) => (
                  <option key={s.subject_code} value={s.subject_code}>
                    {s.display_name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="gen-q-topic"
                className="block text-sm font-medium"
              >
                Topic
              </label>
              <select
                id="gen-q-topic"
                value={topicId}
                onChange={(e) => setTopicId(e.target.value)}
                disabled={isSubmitting}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="">All extracted topics</option>
                {topics.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="gen-q-difficulty"
                className="block text-sm font-medium"
              >
                Difficulty
              </label>
              <select
                id="gen-q-difficulty"
                value={difficulty}
                onChange={(e) =>
                  setDifficulty(
                    e.target.value as "easy" | "medium" | "hard" | "mixed",
                  )
                }
                disabled={isSubmitting}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="mixed">Mixed</option>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="gen-q-count"
                className="block text-sm font-medium"
              >
                Question Count
              </label>
              <input
                id="gen-q-count"
                type="number"
                min={1}
                max={25}
                value={count}
                onChange={(e) =>
                  setCount(Math.max(1, Math.min(25, Number(e.target.value) || 5)))
                }
                disabled={isSubmitting}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
          </div>

          {errorMessage ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
            >
              <AlertCircle
                className="mt-0.5 h-4 w-4 shrink-0"
                aria-hidden="true"
              />
              <span>{errorMessage}</span>
            </div>
          ) : null}

          {resultSummary ? (
            <div
              role="status"
              className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"
            >
              <CheckCircle2
                className="mt-0.5 h-4 w-4 shrink-0"
                aria-hidden="true"
              />
              <span>
                Created {resultSummary.created.length} questions (
                {resultSummary.verified_count} verified,{" "}
                {resultSummary.needs_review_count} needs review,{" "}
                {resultSummary.duplicates_skipped} duplicates skipped).
              </span>
            </div>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={isSubmitting}
              onClick={onClose}
            >
              Close
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              <span>{isSubmitting ? "Generating…" : "Generate"}</span>
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
