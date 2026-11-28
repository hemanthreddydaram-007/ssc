"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, Sparkles, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SubjectOut } from "@/lib/api/knowledge";
import {
  importQuestions,
  type ImportQuestionItem,
  type ImportQuestionsResponse,
} from "@/lib/api/questions";
import { cn } from "@/lib/utils/cn";

interface ImportQuestionsDialogProps {
  open: boolean;
  subjects: readonly SubjectOut[];
  onClose: () => void;
  onImported: (result: ImportQuestionsResponse) => void;
}

type ImportFormat = "json" | "csv";

const FALLBACK_SUBJECTS: readonly {
  subject_code: string;
  display_name: string;
}[] = [
  { subject_code: "quantitative_aptitude", display_name: "Quantitative Aptitude / Maths" },
  { subject_code: "reasoning", display_name: "General Intelligence / Reasoning" },
  { subject_code: "english", display_name: "English Language" },
  { subject_code: "general_awareness", display_name: "General Awareness" },
  { subject_code: "unknown", display_name: "General / Unknown" },
];

const SAMPLE_PYQS_JSON = JSON.stringify(
  [
    {
      question_text:
        "If 15% of x is equal to 25% of 60, what is the value of x?",
      options: [
        { key: "A", text: "80" },
        { key: "B", text: "100" },
        { key: "C", text: "120" },
        { key: "D", text: "90" },
      ],
      correct_option_key: "B",
      explanation: "0.15 * x = 0.25 * 60 = 15, so x = 15 / 0.15 = 100.",
      subject_code: "quantitative_aptitude",
      topic_name: "Percentage",
      difficulty: "easy",
    },
    {
      question_text:
        "A train 180 m long crosses a pole in 9 seconds. What is its speed in km/h?",
      options: [
        { key: "A", text: "60 km/h" },
        { key: "B", text: "72 km/h" },
        { key: "C", text: "64 km/h" },
        { key: "D", text: "80 km/h" },
      ],
      correct_option_key: "B",
      explanation: "Speed = 180 / 9 = 20 m/s = 20 * (18 / 5) = 72 km/h.",
      subject_code: "quantitative_aptitude",
      topic_name: "Time, Speed and Distance",
      difficulty: "medium",
    },
  ],
  null,
  2,
);

const SAMPLE_PYQS_CSV = [
  "question_text,option_a,option_b,option_c,option_d,correct_option_key,explanation,subject_code,topic_name,difficulty",
  '"If 15% of x is equal to 25% of 60, what is the value of x?",80,100,120,90,B,"0.15 * x = 15, so x = 100.",quantitative_aptitude,Percentage,easy',
  '"A train 180 m long crosses a pole in 9 seconds. What is its speed in km/h?",60 km/h,72 km/h,64 km/h,80 km/h,B,"Speed = 20 m/s = 72 km/h.",quantitative_aptitude,"Time, Speed and Distance",medium',
].join("\n");

export function ImportQuestionsDialog({
  open,
  subjects,
  onClose,
  onImported,
}: ImportQuestionsDialogProps) {
  const subjectOptions =
    subjects.length > 0 ? subjects : FALLBACK_SUBJECTS;

  const [format, setFormat] = React.useState<ImportFormat>("json");
  const [defaultSubject, setDefaultSubject] = React.useState(
    "quantitative_aptitude",
  );
  const [provenance, setProvenance] = React.useState<
    "user_supplied" | "source_answer_key"
  >("user_supplied");
  const [rawJson, setRawJson] = React.useState("");
  const [rawCsv, setRawCsv] = React.useState("");
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

  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, isSubmitting, onClose]);

  if (!open) {
    return null;
  }

  const handleLoadSample = () => {
    setErrorMessage(null);
    setResultSummary(null);
    setDefaultSubject("quantitative_aptitude");
    setProvenance("source_answer_key");
    if (format === "json") {
      setRawJson(SAMPLE_PYQS_JSON);
    } else {
      setRawCsv(SAMPLE_PYQS_CSV);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    setResultSummary(null);

    const subjectCode = defaultSubject.trim() || "unknown";

    if (format === "csv") {
      const trimmedCsv = rawCsv.trim();
      if (!trimmedCsv) {
        setErrorMessage("Paste CSV rows (including header line) before importing.");
        return;
      }

      setIsSubmitting(true);
      try {
        const res = await importQuestions({
          default_subject_code: subjectCode,
          answer_key_provenance: provenance,
          items: [],
          csv_content: trimmedCsv,
        });
        setResultSummary(res);
        setRawCsv("");
        onImported(res);
      } catch (error) {
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to import CSV questions.",
        );
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(rawJson);
    } catch {
      setErrorMessage(
        "Invalid JSON format. Provide an array of question objects or click Load Sample PYQs.",
      );
      return;
    }

    const items: ImportQuestionItem[] = Array.isArray(parsed)
      ? (parsed as ImportQuestionItem[])
      : typeof parsed === "object" &&
          parsed !== null &&
          Array.isArray((parsed as { items?: unknown }).items)
        ? (parsed as { items: ImportQuestionItem[] }).items
        : [];

    if (items.length === 0) {
      setErrorMessage("Provide at least one question item in JSON.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await importQuestions({
        default_subject_code: subjectCode,
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
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-lg border bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="import-q-title" className="text-lg font-semibold">
              Import Previous-Year Questions (PYQs)
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Import structured MCQs via JSON or CSV. You can load sample SSC
              questions to test right away.
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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div
              role="tablist"
              aria-label="Import format"
              className="inline-flex shrink-0 rounded-md border bg-muted p-1"
            >
              <button
                type="button"
                role="tab"
                aria-selected={format === "json"}
                onClick={() => {
                  setFormat("json");
                  setErrorMessage(null);
                }}
                className={cn(
                  "whitespace-nowrap rounded px-3 py-1 text-xs font-medium transition-colors",
                  format === "json"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                JSON Format
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={format === "csv"}
                onClick={() => {
                  setFormat("csv");
                  setErrorMessage(null);
                }}
                className={cn(
                  "whitespace-nowrap rounded px-3 py-1 text-xs font-medium transition-colors",
                  format === "csv"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                CSV Format
              </button>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isSubmitting}
              onClick={handleLoadSample}
            >
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Load Sample PYQs</span>
            </Button>
          </div>

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
                {subjectOptions.map((s) => (
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
                Answer-Key Source
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
                <option value="user_supplied">
                  User supplied (needs review)
                </option>
                <option value="source_answer_key">
                  Official source key (auto-verified)
                </option>
              </select>
            </div>
          </div>

          <p className="rounded-md bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
            {provenance === "source_answer_key" ? (
              <>
                <strong>Official source key:</strong> Questions with complete
                options and answer keys are marked <em>Verified</em> immediately
                for mock tests.
              </>
            ) : (
              <>
                <strong>User supplied:</strong> Imported questions start as{" "}
                <em>Needs review</em> so you can double-check keys (or toggle
                &ldquo;Include unreviewed questions&rdquo; in Test Builder).
              </>
            )}
          </p>

          {format === "json" ? (
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
          ) : (
            <div>
              <label
                htmlFor="import-q-csv"
                className="block text-sm font-medium"
              >
                Questions CSV Content
              </label>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                Columns: <code>question_text</code>, <code>option_a</code>..
                <code>option_d</code>, <code>correct_option_key</code>, optional{" "}
                <code>explanation</code>, <code>subject_code</code>,{" "}
                <code>topic_name</code>, <code>difficulty</code>.
              </p>
              <textarea
                id="import-q-csv"
                rows={7}
                value={rawCsv}
                onChange={(e) => setRawCsv(e.target.value)}
                disabled={isSubmitting}
                placeholder="question_text,option_a,option_b,option_c,option_d,correct_option_key,difficulty"
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
              />
            </div>
          )}

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
              <span>{isSubmitting ? "Importing…" : "Import Questions"}</span>
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
