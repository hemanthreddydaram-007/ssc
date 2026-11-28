"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, FileText, Loader2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatBytes, type DocumentItem } from "@/lib/api/documents";
import type { PdfPipelineProgress } from "@/lib/workflows/pdfPipeline";
import { cn } from "@/lib/utils/cn";

interface QuickPdfDropCardProps {
  title: string;
  description: string;
  actionLabel: string;
  busyLabel?: string;
  existingDocuments?: readonly DocumentItem[];
  isRunning: boolean;
  progress: PdfPipelineProgress | null;
  errorMessage: string | null;
  successAction?: React.ReactNode;
  extraControls?: React.ReactNode;
  onRun: (selection: { file: File | null; documentId: string }) => void;
}

export function QuickPdfDropCard({
  title,
  description,
  actionLabel,
  busyLabel = "Working…",
  existingDocuments = [],
  isRunning,
  progress,
  errorMessage,
  successAction,
  extraControls,
  onRun,
}: QuickPdfDropCardProps) {
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [selectedDocId, setSelectedDocId] = React.useState("");
  const [isDragging, setIsDragging] = React.useState(false);
  const [localError, setLocalError] = React.useState<string | null>(null);
  const inputId = React.useId();

  const pickFile = (file: File | undefined) => {
    setLocalError(null);
    if (!file) {
      setSelectedFile(null);
      return;
    }
    const lower = file.name.toLowerCase();
    if (
      !lower.endsWith(".pdf") &&
      !lower.endsWith(".jpg") &&
      !lower.endsWith(".jpeg") &&
      !lower.endsWith(".png")
    ) {
      setLocalError("Upload a PDF, JPG, or PNG file.");
      return;
    }
    if (file.size === 0) {
      setLocalError("Selected file is empty.");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setLocalError("File exceeds 50 MB limit.");
      return;
    }
    setSelectedFile(file);
    setSelectedDocId("");
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setLocalError(null);
    if (!selectedFile && !selectedDocId) {
      setLocalError("Drop a PDF file or pick an existing document.");
      return;
    }
    onRun({ file: selectedFile, documentId: selectedDocId });
  };

  const displayError = localError || errorMessage;

  return (
    <Card className="border-primary/25 bg-primary/[0.02]">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-12 lg:items-stretch">
            <div
              className={cn(
                existingDocuments.length > 0 ? "lg:col-span-7" : "lg:col-span-12",
              )}
            >
              <input
                id={inputId}
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                disabled={isRunning}
                onChange={(e) => pickFile(e.target.files?.[0])}
                className="sr-only"
              />
              <label
                htmlFor={inputId}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (!isRunning) setIsDragging(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (!isRunning) pickFile(e.dataTransfer.files?.[0]);
                }}
                className={cn(
                  "flex h-full min-h-[84px] cursor-pointer items-center gap-3 rounded-lg border-2 border-dashed bg-background px-4 py-3 transition-colors",
                  isDragging
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/60",
                  isRunning && "pointer-events-none opacity-60",
                )}
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <Upload className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  {selectedFile ? (
                    <>
                      <p className="truncate text-sm font-medium text-foreground">
                        {selectedFile.name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatBytes(selectedFile.size)} · Click or drop to replace
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-sm font-medium">
                        Drop a PDF here, or{" "}
                        <span className="text-primary underline">browse</span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        PDF, JPG, or PNG · One click from file to output
                      </p>
                    </>
                  )}
                </div>
              </label>
            </div>

            {existingDocuments.length > 0 ? (
              <div className="flex flex-col justify-center rounded-lg border bg-background px-3.5 py-2.5 lg:col-span-5">
                <label
                  htmlFor={`${inputId}-existing`}
                  className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"
                >
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Or use an existing PDF from Library</span>
                </label>
                <select
                  id={`${inputId}-existing`}
                  value={selectedDocId}
                  disabled={isRunning}
                  onChange={(e) => {
                    setSelectedDocId(e.target.value);
                    if (e.target.value) setSelectedFile(null);
                    setLocalError(null);
                  }}
                  className="mt-1.5 w-full min-w-0 max-w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">Choose uploaded PDF…</option>
                  {existingDocuments.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.title} ({doc.page_count}p)
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
          </div>

          {extraControls ? (
            <div className="flex flex-wrap items-center gap-3">{extraControls}</div>
          ) : null}

          {progress ? (
            <div
              role="status"
              aria-live="polite"
              className={cn(
                "space-y-1.5 rounded-md border p-3",
                progress.percent >= 100
                  ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                  : "bg-background",
              )}
            >
              <div className="flex items-center justify-between gap-2 text-xs font-medium">
                <span className="inline-flex items-center gap-1.5">
                  {progress.percent >= 100 ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
                  ) : (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" aria-hidden="true" />
                  )}
                  <span>{progress.stepLabel}</span>
                </span>
                <span>{progress.percent}%</span>
              </div>
              <p className="text-xs text-muted-foreground">{progress.detail}</p>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className={cn(
                    "h-full transition-all duration-300",
                    progress.percent >= 100 ? "bg-emerald-600" : "bg-primary",
                  )}
                  style={{ width: `${progress.percent}%` }}
                />
              </div>
              {progress.percent >= 100 && successAction ? (
                <div className="pt-1">{successAction}</div>
              ) : null}
            </div>
          ) : null}

          {displayError ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-800"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{displayError}</span>
            </div>
          ) : null}

          <div className="flex items-center justify-end">
            <Button
              type="submit"
              disabled={isRunning || (!selectedFile && !selectedDocId)}
            >
              {isRunning ? busyLabel : actionLabel}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
