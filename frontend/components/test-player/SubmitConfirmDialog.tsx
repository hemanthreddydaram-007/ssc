"use client";

import { AlertTriangle, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { PaletteItemOut } from "@/lib/api/attempts";

interface SubmitConfirmDialogProps {
  open: boolean;
  palette: readonly PaletteItemOut[];
  isSubmitting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function SubmitConfirmDialog({
  open,
  palette,
  isSubmitting,
  onClose,
  onConfirm,
}: SubmitConfirmDialogProps) {
  if (!open) {
    return null;
  }

  const answeredCount = palette.filter(
    (p) => p.has_answer || p.status === "answered",
  ).length;
  const skippedCount = palette.filter((p) => p.status === "skipped").length;
  const reviewCount = palette.filter((p) => p.is_marked_for_review).length;
  const unvisitedCount = palette.filter((p) => p.status === "unvisited").length;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="submit-confirm-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4 backdrop-blur-sm"
    >
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <AlertTriangle
              className="h-5 w-5 text-amber-600"
              aria-hidden="true"
            />
            <h2 id="submit-confirm-title" className="text-lg font-semibold">
              Submit Test Attempt?
            </h2>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Close confirmation"
            disabled={isSubmitting}
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        <p className="mt-2 text-sm text-muted-foreground">
          Once submitted, your answers will be graded by the server and cannot
          be changed.
        </p>

        <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
          <div className="rounded-md border bg-muted/40 p-2.5">
            <dt className="text-xs text-muted-foreground">Answered</dt>
            <dd className="font-semibold text-emerald-700">{answeredCount}</dd>
          </div>
          <div className="rounded-md border bg-muted/40 p-2.5">
            <dt className="text-xs text-muted-foreground">Unvisited</dt>
            <dd className="font-semibold">{unvisitedCount}</dd>
          </div>
          <div className="rounded-md border bg-muted/40 p-2.5">
            <dt className="text-xs text-muted-foreground">Skipped</dt>
            <dd className="font-semibold text-amber-700">{skippedCount}</dd>
          </div>
          <div className="rounded-md border bg-muted/40 p-2.5">
            <dt className="text-xs text-muted-foreground">Marked Review</dt>
            <dd className="font-semibold text-violet-700">{reviewCount}</dd>
          </div>
        </dl>

        <div className="mt-5 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={isSubmitting}
            onClick={onClose}
          >
            Keep Practising
          </Button>
          <Button type="button" disabled={isSubmitting} onClick={onConfirm}>
            {isSubmitting ? "Submitting…" : "Confirm Submit"}
          </Button>
        </div>
      </div>
    </div>
  );
}
