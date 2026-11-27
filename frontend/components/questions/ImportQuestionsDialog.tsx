"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SubjectOut } from "@/lib/api/knowledge";
import {
  importQuestions,
  type ImportQuestionItem,
  type ImportQuestionsResponse,
} from "@/lib/api/questions";

interface ImportQuestionsDialogProps {
  open: boolean;
  subjects: readonly SubjectOut[];
  onClose: () => void;
  onImported: (result: ImportQuestionsResponse) => void;
}

export function ImportQuestionsDialog({
  open,
  subjects,
  onClose,
  onImported,
}: ImportQuestionsDialogProps) {
  const [defaultSubject, setDefaultSubject] = React.useState(
    "quantitative_aptitude",
  );
  const [provenance, setProvenance] = React.useState<
    "user_supplied" | "source_answer_key"
  >("user_supplied");
  const [rawJson, setRawJson] = React.useState("");
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [resultSummary, setResultSummary] =
    React.useState<ImportQuestionsResponse | null>(null);

  React.useEffect(() => {
    if (open) {
      setErrorMessage(null);
      setResultSummary(null);
    }
  }, [open]);

  if (!open) {
    return null;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    setResultSummary(null);

    let parsed: unknown;
    try {
      parsed = JSON.parse(rawJson);
    } catch {
      setErrorMessage("Invalid JSON format. Provide an array of question objects.");
      return;
    }

    const items: ImportQuestionItem[] = Array.isArray(parsed)
      ? (parsed as ImportQuestionItem[])
      : typeof parsed === "object" &&
          parsed !== null &&
          Array.isArray((parsed as { items?: unknown }).items)
        ? ((parsed as { items: ImportQuestionItem[] }).items)
        : [];

    if (items.length === 0) {
      setErrorMessage("Provide at least one question item in JSON.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await importQuestions({
        default_subject_code: defaultSubject || null,
        answer_key_provenance: provenance,
        items,
      });
      setResultSummary(res);
      setRawJson("");
      onImported(res);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to import questions.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-q-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-xl rounded-lg border bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="import-q-title" className="text-lg font-semibold">
              Import Questions (JSON)
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Import structured PYQs or question sets. User-supplied keys are
              marked for review unless verified by deterministic checks.
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
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor="import-q-subject"
                className="block text-sm font-medium"
              >
                Default Subject
              </label>
              <select
                id="import-q-subject"
                value={defaultSubject}
                onChange={(e) => setDefaultSubject(e.target.value)}
                disabled={isSubmitting}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {subjects.map((s) => (
                  <option key={s.subject_code} value={s.subject_code}>
                    {s.display_name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="import-q-provenance"
                className="block text-sm font-medium"
              >
                Answer-Key Provenance
              </label>
              <select
                id="import-q-provenance"
                value={provenance}
                onChange={(e) =>
                  setProvenance(
                    e.target.value as "user_supplied" | "source_answer_key",
                  )
                }
                disabled={isSubmitting}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="user_supplied">User supplied (needs review)</option>
                <option value="source_answer_key">Official source key</option>
              </select>
            </div>
          </div>

          <div>
            <label
              htmlFor="import-q-json"
              className="block text-sm font-medium"
            >
              Questions JSON Array
            </label>
            <textarea
              id="import-q-json"
              rows={7}
              value={rawJson}
              onChange={(e) => setRawJson(e.target.value)}
              disabled={isSubmitting}
              placeholder='[{"question_text":"What is 25% of 80?","options":[{"key":"A","text":"15"},{"key":"B","text":"20"},{"key":"C","text":"25"},{"key":"D","text":"30"}],"correct_option_key":"B","difficulty":"easy"}]'
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
            />
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
                Imported {resultSummary.imported_count} questions (
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
              <Upload className="h-4 w-4" aria-hidden="true" />
              <span>{isSubmitting ? "Importing…" : "Import"}</span>
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
