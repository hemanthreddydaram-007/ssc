"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Edit3,
  FileText,
  Trash2,
  X,
} from "lucide-react";

import { AuthAssetImage } from "@/components/common/AuthAssetImage";
import { RichMathText } from "@/components/common/MathRenderer";
import { getValidationBadgeVariant } from "@/components/questions/QuestionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import {
  deleteQuestion,
  getQuestionDetail,
  updateQuestion,
  type QuestionDetailOut,
} from "@/lib/api/questions";
import { cn } from "@/lib/utils/cn";

interface QuestionDetailDrawerProps {
  questionId: string | null;
  onClose: () => void;
  onQuestionUpdated: (updated: QuestionDetailOut) => void;
  onQuestionDeleted: (questionId: string) => void;
}

export function QuestionDetailDrawer({
  questionId,
  onClose,
  onQuestionUpdated,
  onQuestionDeleted,
}: QuestionDetailDrawerProps) {
  const [detail, setDetail] = React.useState<QuestionDetailOut | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const [isEditing, setIsEditing] = React.useState(false);
  const [editCorrectKey, setEditCorrectKey] = React.useState("");
  const [editExplanation, setEditExplanation] = React.useState("");
  const [editDifficulty, setEditDifficulty] = React.useState("medium");
  const [isSaving, setIsSaving] = React.useState(false);
  const [isDeleting, setIsDeleting] = React.useState(false);

  React.useEffect(() => {
    if (!questionId) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setIsLoading(true);
    setErrorMessage(null);
    setIsEditing(false);

    getQuestionDetail(questionId, controller.signal)
      .then((loaded) => {
        setDetail(loaded);
        setEditCorrectKey(loaded.correct_answer_data?.correct_option_key ?? "");
        setEditExplanation(loaded.explanation ?? "");
        setEditDifficulty(loaded.difficulty);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load question details.",
        );
      })
      .finally(() => setIsLoading(false));

    return () => controller.abort();
  }, [questionId]);

  React.useEffect(() => {
    if (!questionId) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [questionId, onClose]);

  if (!questionId) {
    return null;
  }

  const handleStatusChange = async (nextStatus: string) => {
    if (!detail) return;
    setIsSaving(true);
    setErrorMessage(null);
    try {
      const updated = await updateQuestion(detail.id, {
        validation_status: nextStatus,
      });
      setDetail(updated);
      onQuestionUpdated(updated);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to update status.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveEdit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!detail) return;
    setIsSaving(true);
    setErrorMessage(null);
    try {
      const updated = await updateQuestion(detail.id, {
        correct_option_key: editCorrectKey || undefined,
        explanation: editExplanation,
        difficulty: editDifficulty,
      });
      setDetail(updated);
      setIsEditing(false);
      onQuestionUpdated(updated);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to save edits.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!detail) return;
    setIsDeleting(true);
    setErrorMessage(null);
    try {
      await deleteQuestion(detail.id);
      onQuestionDeleted(detail.id);
      onClose();
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to delete question.",
      );
      setIsDeleting(false);
    }
  };

  const correctKey = detail?.correct_answer_data?.correct_option_key ?? null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Question review details"
      className="fixed inset-0 z-50 flex justify-end bg-foreground/40 backdrop-blur-sm"
    >
      <div
        className="fixed inset-0"
        aria-hidden="true"
        onClick={onClose}
      />
      <div className="relative z-10 flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l bg-card p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b pb-4">
          <div>
            <h2 className="text-lg font-semibold">
              Question Bank Review
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Answer keys and explanations are shown here for bank review only
              (never exposed in active tests).
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Close question drawer"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        <div className="mt-5 flex-1 space-y-5">
          {isLoading ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              Loading question details…
            </p>
          ) : errorMessage && !detail ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{errorMessage}</span>
            </div>
          ) : detail ? (
            <>
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

              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="outline">
                  {formatSubjectLabel(detail.subject_code)}
                </Badge>
                {detail.topic_name ? (
                  <Badge variant="outline">{detail.topic_name}</Badge>
                ) : null}
                <Badge variant="secondary" className="capitalize">
                  {detail.difficulty}
                </Badge>
                <Badge variant="outline" className="capitalize">
                  {detail.origin}
                </Badge>
                <Badge
                  variant={getValidationBadgeVariant(detail.validation_status)}
                >
                  {detail.validation_status.replace(/_/g, " ")}
                </Badge>
              </div>

              {detail.validation_warnings &&
              detail.validation_warnings.length > 0 ? (
                <div className="space-y-1 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <p className="flex items-center gap-1.5 font-semibold">
                    <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                    Validation warnings
                  </p>
                  <ul className="list-disc pl-5">
                    {detail.validation_warnings.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {detail.passage_text ? (
                <div className="rounded-md border bg-muted/40 p-3 text-sm">
                  <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                    Passage
                  </p>
                  <RichMathText text={detail.passage_text} />
                </div>
              ) : null}

              {detail.diagram_asset_id && detail.document_id ? (
                <div className="overflow-hidden rounded-md border bg-muted/20 p-2">
                  <AuthAssetImage
                    documentId={detail.document_id}
                    assetId={detail.diagram_asset_id}
                    alt="Question diagram"
                    className="mx-auto max-h-56 w-auto rounded object-contain"
                  />
                </div>
              ) : null}

              <div className="text-base font-medium">
                <RichMathText text={detail.question_text} />
              </div>

              <div className="space-y-2">
                {detail.options.map((opt) => {
                  const isCorrect =
                    correctKey !== null && opt.option_key === correctKey;
                  return (
                    <div
                      key={opt.option_key}
                      className={cn(
                        "flex items-start justify-between gap-2 rounded-md border px-3 py-2 text-sm",
                        isCorrect
                          ? "border-emerald-300 bg-emerald-50/70"
                          : "bg-muted/20",
                      )}
                    >
                      <div className="flex items-start gap-2">
                        <span className="font-semibold">
                          ({opt.option_key})
                        </span>
                        <RichMathText text={opt.option_text} />
                      </div>
                      {isCorrect ? (
                        <Badge variant="success">Correct</Badge>
                      ) : null}
                    </div>
                  );
                })}
              </div>

              {isEditing ? (
                <form
                  onSubmit={handleSaveEdit}
                  className="space-y-3 rounded-md border bg-muted/30 p-4"
                >
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label
                        htmlFor="edit-q-correct"
                        className="block text-xs font-medium"
                      >
                        Correct Option Key
                      </label>
                      <select
                        id="edit-q-correct"
                        value={editCorrectKey}
                        onChange={(e) => setEditCorrectKey(e.target.value)}
                        className="mt-1 w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
                      >
                        <option value="">Unset</option>
                        {detail.options.map((opt) => (
                          <option key={opt.option_key} value={opt.option_key}>
                            {opt.option_key}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label
                        htmlFor="edit-q-difficulty"
                        className="block text-xs font-medium"
                      >
                        Difficulty
                      </label>
                      <select
                        id="edit-q-difficulty"
                        value={editDifficulty}
                        onChange={(e) => setEditDifficulty(e.target.value)}
                        className="mt-1 w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
                      >
                        <option value="easy">Easy</option>
                        <option value="medium">Medium</option>
                        <option value="hard">Hard</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label
                      htmlFor="edit-q-explanation"
                      className="block text-xs font-medium"
                    >
                      Explanation
                    </label>
                    <textarea
                      id="edit-q-explanation"
                      rows={4}
                      value={editExplanation}
                      onChange={(e) => setEditExplanation(e.target.value)}
                      className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>

                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={isSaving}
                      onClick={() => setIsEditing(false)}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" size="sm" disabled={isSaving}>
                      {isSaving ? "Saving…" : "Save Changes"}
                    </Button>
                  </div>
                </form>
              ) : (
                <div className="rounded-md border bg-muted/30 p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold">Explanation</h3>
                    <span className="text-xs text-muted-foreground">
                      Answer provenance:{" "}
                      {detail.answer_key_provenance.replace(/_/g, " ")}
                    </span>
                  </div>
                  {detail.explanation ? (
                    <div className="text-sm">
                      <RichMathText text={detail.explanation} />
                    </div>
                  ) : (
                    <p className="text-xs italic text-muted-foreground">
                      No explanation recorded yet.
                    </p>
                  )}
                </div>
              )}

              {/* Provenance */}
              <div className="rounded-md border p-3 text-xs text-muted-foreground space-y-1.5">
                <p className="font-semibold text-foreground">
                  Source &amp; Provenance
                </p>
                {detail.document_id ? (
                  <p>
                    Document:{" "}
                    <Link
                      href={`/documents/${encodeURIComponent(detail.document_id)}${detail.source_page_number ? `?tab=source_pages&page=${detail.source_page_number}` : ""}`}
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      <FileText className="h-3 w-3" aria-hidden="true" />
                      Open source
                      {detail.source_page_number
                        ? ` (Page ${detail.source_page_number})`
                        : ""}
                    </Link>
                  </p>
                ) : (
                  <p>Standalone / imported question</p>
                )}
                {detail.supporting_excerpt ? (
                  <p className="italic">
                    Excerpt: &ldquo;{detail.supporting_excerpt}&rdquo;
                  </p>
                ) : null}
                {detail.model_name ? (
                  <p>
                    Model: {detail.model_name} ({detail.prompt_version ?? "v1"})
                  </p>
                ) : null}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
                <div className="flex flex-wrap items-center gap-2">
                  {detail.validation_status !== "verified" ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={isSaving}
                      onClick={() => void handleStatusChange("verified")}
                    >
                      <CheckCircle2
                        className="h-4 w-4 text-emerald-600"
                        aria-hidden="true"
                      />
                      <span>Mark Verified</span>
                    </Button>
                  ) : null}
                  {detail.validation_status !== "needs_review" ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={isSaving}
                      onClick={() => void handleStatusChange("needs_review")}
                    >
                      <span>Flag Needs Review</span>
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={isSaving}
                    onClick={() => setIsEditing((prev) => !prev)}
                  >
                    <Edit3 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>{isEditing ? "Close Editor" : "Edit Answer"}</span>
                  </Button>
                </div>

                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  disabled={isDeleting}
                  onClick={() => void handleDelete()}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{isDeleting ? "Deleting…" : "Delete"}</span>
                </Button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
