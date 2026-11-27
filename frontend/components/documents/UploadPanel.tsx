"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  FileUp,
  Upload,
} from "lucide-react";

import {
  DocumentMetadataFields,
  type MetadataFormValues,
} from "@/components/documents/DocumentMetadataFields";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiError } from "@/lib/api/client";
import {
  createTextDocument,
  formatBytes,
  uploadDocumentFile,
  type DocumentItem,
} from "@/lib/api/documents";
import type { ExamConfig } from "@/lib/api/examConfigs";
import { cn } from "@/lib/utils/cn";
import { loadPreferences } from "@/lib/utils/preferences";

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"] as const;
const ALLOWED_MIME_TYPES = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
]);

interface UploadPanelProps {
  examConfigs: readonly ExamConfig[];
  examConfigsLoading: boolean;
  onDocumentCreated: (doc: DocumentItem) => void;
}

type UploadMode = "file" | "text";

interface DuplicateNotice {
  message: string;
  existingDocumentId?: string;
}

function validateSelectedFile(file: File): string | null {
  const lowerName = file.name.toLowerCase();
  const hasAllowedExt = ALLOWED_EXTENSIONS.some((ext) =>
    lowerName.endsWith(ext),
  );
  if (!hasAllowedExt && !ALLOWED_MIME_TYPES.has(file.type)) {
    return "Unsupported file type. Upload a PDF, JPG, or PNG file.";
  }
  if (file.size === 0) {
    return "Selected file is empty.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `File exceeds the 50 MB limit (${formatBytes(file.size)}).`;
  }
  return null;
}

function createInitialMetadata(examConfigs: readonly ExamConfig[]): MetadataFormValues {
  const preferredCode = loadPreferences().default_exam_code;
  const defaultExam =
    examConfigs.find((c) => c.exam_code === preferredCode) ??
    examConfigs.find((c) => c.exam_code === "ssc_chsl_tier_1");
  return {
    title: "",
    exam_config_id: defaultExam?.id ?? "",
    subject_code: "",
    material_type: "other",
    language: "en",
    chapter_or_topic_hint: "",
    source_label: "",
  };
}

export function UploadPanel({
  examConfigs,
  examConfigsLoading,
  onDocumentCreated,
}: UploadPanelProps) {
  const [mode, setMode] = React.useState<UploadMode>("file");
  const [metadata, setMetadata] = React.useState<MetadataFormValues>(() =>
    createInitialMetadata(examConfigs),
  );
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [pastedText, setPastedText] = React.useState("");
  const [isDragging, setIsDragging] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [uploadPercent, setUploadPercent] = React.useState<number | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [duplicateNotice, setDuplicateNotice] =
    React.useState<DuplicateNotice | null>(null);
  const [successDoc, setSuccessDoc] = React.useState<DocumentItem | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Set default exam_config_id once examConfigs load if user has not picked one yet
  React.useEffect(() => {
    if (metadata.exam_config_id === "" && examConfigs.length > 0) {
      const preferredCode = loadPreferences().default_exam_code;
      const defaultExam =
        examConfigs.find((c) => c.exam_code === preferredCode) ??
        examConfigs.find((c) => c.exam_code === "ssc_chsl_tier_1");
      if (defaultExam) {
        setMetadata((prev) =>
          prev.exam_config_id === ""
            ? { ...prev, exam_config_id: defaultExam.id }
            : prev,
        );
      }
    }
  }, [examConfigs, metadata.exam_config_id]);

  const clearFeedback = () => {
    setErrorMessage(null);
    setDuplicateNotice(null);
    setSuccessDoc(null);
  };

  const handlePickFile = (file: File | undefined) => {
    clearFeedback();
    if (!file) {
      setSelectedFile(null);
      return;
    }
    const validationError = validateSelectedFile(file);
    if (validationError) {
      setSelectedFile(null);
      setErrorMessage(validationError);
      return;
    }
    setSelectedFile(file);
  };

  const submitFileUpload = async (allowDuplicate: boolean) => {
    if (!selectedFile) {
      setErrorMessage("Please select a PDF, JPG, or PNG file first.");
      return;
    }
    const validationError = validateSelectedFile(selectedFile);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    clearFeedback();
    setIsSubmitting(true);
    setUploadPercent(0);

    try {
      const created = await uploadDocumentFile({
        file: selectedFile,
        title: metadata.title || undefined,
        exam_config_id: metadata.exam_config_id || null,
        subject_code: metadata.subject_code || null,
        material_type: metadata.material_type || "other",
        language: metadata.language || "en",
        chapter_or_topic_hint: metadata.chapter_or_topic_hint || null,
        source_label: metadata.source_label || null,
        allow_duplicate: allowDuplicate,
        onProgress: (pct) => setUploadPercent(pct),
      });
      setSuccessDoc(created);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setMetadata((prev) => ({
        ...createInitialMetadata(examConfigs),
        exam_config_id: prev.exam_config_id,
      }));
      onDocumentCreated(created);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setDuplicateNotice({
          message: error.message,
          existingDocumentId: error.existingDocumentId,
        });
      } else if (error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unexpected error while uploading document.");
      }
    } finally {
      setIsSubmitting(false);
      setUploadPercent(null);
    }
  };

  const submitTextUpload = async (allowDuplicate: boolean) => {
    const trimmedTitle = metadata.title.trim();
    const trimmedContent = pastedText.trim();
    if (!trimmedTitle) {
      setErrorMessage("Title is required when pasting plain text.");
      return;
    }
    if (!trimmedContent) {
      setErrorMessage("Please paste study text or questions before submitting.");
      return;
    }

    clearFeedback();
    setIsSubmitting(true);

    try {
      const created = await createTextDocument({
        title: trimmedTitle,
        content: trimmedContent,
        exam_config_id: metadata.exam_config_id || null,
        subject_code: metadata.subject_code || null,
        material_type: metadata.material_type || "other",
        language: metadata.language || "en",
        chapter_or_topic_hint: metadata.chapter_or_topic_hint || null,
        source_label: metadata.source_label || null,
        allow_duplicate: allowDuplicate,
      });
      setSuccessDoc(created);
      setPastedText("");
      setMetadata((prev) => ({
        ...createInitialMetadata(examConfigs),
        exam_config_id: prev.exam_config_id,
      }));
      onDocumentCreated(created);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setDuplicateNotice({
          message: error.message,
          existingDocumentId: error.existingDocumentId,
        });
      } else if (error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unexpected error while saving text material.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (mode === "file") {
      void submitFileUpload(false);
    } else {
      void submitTextUpload(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Upload Study Material</CardTitle>
            <CardDescription>
              Accepted files: PDF, JPG, PNG (up to 50 MB / 250 PDF pages) or
              paste plain text. Stored privately on the server.
            </CardDescription>
          </div>
          <div
            role="tablist"
            aria-label="Upload mode"
            className="inline-flex rounded-md border bg-muted p-1"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mode === "file"}
              onClick={() => {
                setMode("file");
                clearFeedback();
              }}
              className={cn(
                "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors",
                mode === "file"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <FileUp className="h-3.5 w-3.5" aria-hidden="true" />
              <span>File Upload</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "text"}
              onClick={() => {
                setMode("text");
                clearFeedback();
              }}
              className={cn(
                "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors",
                mode === "text"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <FileText className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Paste Text</span>
            </button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          {mode === "file" ? (
            <div>
              <input
                ref={fileInputRef}
                id="material-file-input"
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                onChange={(e) => handlePickFile(e.target.files?.[0])}
                disabled={isSubmitting}
                className="sr-only"
              />
              <label
                htmlFor="material-file-input"
                onDragOver={(e) => {
                  e.preventDefault();
                  if (!isSubmitting) setIsDragging(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (!isSubmitting) {
                    handlePickFile(e.dataTransfer.files?.[0]);
                  }
                }}
                className={cn(
                  "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors focus-within:ring-2 focus-within:ring-ring",
                  isDragging
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/60 hover:bg-muted/40",
                  isSubmitting && "pointer-events-none opacity-60",
                )}
              >
                <Upload
                  className="h-8 w-8 text-muted-foreground"
                  aria-hidden="true"
                />
                {selectedFile ? (
                  <div className="mt-3 space-y-1">
                    <p className="text-sm font-medium text-foreground">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatBytes(selectedFile.size)} · Click or drop another
                      file to replace
                    </p>
                  </div>
                ) : (
                  <div className="mt-3 space-y-1">
                    <p className="text-sm font-medium">
                      Drag and drop a PDF or image here, or{" "}
                      <span className="text-primary underline">browse</span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Supports PDF, JPG, PNG · Max 50 MB · Up to 250 PDF pages
                    </p>
                  </div>
                )}
              </label>
            </div>
          ) : (
            <div>
              <label
                htmlFor="pasted-text-content"
                className="block text-sm font-medium"
              >
                Study Text or Questions{" "}
                <span className="text-destructive">*</span>
              </label>
              <textarea
                id="pasted-text-content"
                rows={6}
                value={pastedText}
                onChange={(e) => setPastedText(e.target.value)}
                disabled={isSubmitting}
                placeholder="Paste notes, formulas, or previous-year questions here..."
                className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              />
            </div>
          )}

          <DocumentMetadataFields
            values={metadata}
            onChange={setMetadata}
            examConfigs={examConfigs}
            examConfigsLoading={examConfigsLoading}
            titleRequired={mode === "text"}
            titlePlaceholder={
              mode === "text"
                ? "Enter a descriptive title for this text"
                : "Optional — defaults to uploaded filename"
            }
            disabled={isSubmitting}
            idPrefix={`upload-${mode}`}
          />

          {uploadPercent !== null ? (
            <div className="space-y-1.5" aria-live="polite">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Uploading file bytes…</span>
                <span>{uploadPercent}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full bg-primary transition-all duration-150"
                  style={{ width: `${uploadPercent}%` }}
                />
              </div>
            </div>
          ) : null}

          {errorMessage ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{errorMessage}</span>
            </div>
          ) : null}

          {duplicateNotice ? (
            <div
              role="alert"
              className="flex flex-col gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-start gap-2">
                <AlertCircle
                  className="mt-0.5 h-4 w-4 shrink-0"
                  aria-hidden="true"
                />
                <div>
                  <p className="font-medium">{duplicateNotice.message}</p>
                  <p className="text-xs text-amber-800">
                    An identical file or text content (matching SHA-256 hash) is
                    already in your library.
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {duplicateNotice.existingDocumentId ? (
                  <Button asChild variant="outline" size="sm">
                    <Link
                      href={`/documents/${duplicateNotice.existingDocumentId}`}
                    >
                      Open Existing
                    </Link>
                  </Button>
                ) : null}
                <Button
                  type="button"
                  size="sm"
                  disabled={isSubmitting}
                  onClick={() => {
                    if (mode === "file") {
                      void submitFileUpload(true);
                    } else {
                      void submitTextUpload(true);
                    }
                  }}
                >
                  Upload Anyway
                </Button>
              </div>
            </div>
          ) : null}

          {successDoc ? (
            <div
              role="status"
              aria-live="polite"
              className="flex flex-col gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  Uploaded <strong>{successDoc.title}</strong> ({successDoc.page_count}{" "}
                  {successDoc.page_count === 1 ? "page" : "pages"}).
                </span>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link href={`/documents/${successDoc.id}`}>Open Document</Link>
              </Button>
            </div>
          ) : null}

          <div className="flex justify-end">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? mode === "file"
                  ? "Uploading…"
                  : "Saving…"
                : mode === "file"
                  ? "Upload Material"
                  : "Save Text Material"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
