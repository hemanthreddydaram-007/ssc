"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { BookOpen, CheckCircle2, ExternalLink, Search, X } from "lucide-react";

import { QuickPdfDropCard } from "@/components/documents/QuickPdfDropCard";
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
import { listDocuments, type DocumentItem } from "@/lib/api/documents";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import { listSubjects, type SubjectOut } from "@/lib/api/knowledge";
import {
  formatNoteType,
  listNotes,
  NOTE_TYPE_LABELS,
  type NoteSummaryOut,
} from "@/lib/api/notes";
import {
  runPdfToNotesPipeline,
  type PdfPipelineProgress,
} from "@/lib/workflows/pdfPipeline";

function SmartNotesContent() {
  const searchParams = useSearchParams();
  const initialTopicId = searchParams.get("topic_id") ?? "";

  const [notes, setNotes] = React.useState<NoteSummaryOut[]>([]);
  const [total, setTotal] = React.useState(0);
  const [subjects, setSubjects] = React.useState<SubjectOut[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const [searchQuery, setSearchQuery] = React.useState("");
  const [noteTypeFilter, setNoteTypeFilter] = React.useState("");
  const [subjectFilter, setSubjectFilter] = React.useState("");
  const [topicFilter, setTopicFilter] = React.useState(initialTopicId);
  const [unreviewedOnly, setUnreviewedOnly] = React.useState(false);

  const [documents, setDocuments] = React.useState<DocumentItem[]>([]);
  const [pdfRunning, setPdfRunning] = React.useState(false);
  const [pdfProgress, setPdfProgress] =
    React.useState<PdfPipelineProgress | null>(null);
  const [pdfError, setPdfError] = React.useState<string | null>(null);
  const [generatedNoteId, setGeneratedNoteId] = React.useState<string | null>(
    null,
  );

  React.useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      listSubjects(controller.signal).catch(() => [] as SubjectOut[]),
      listDocuments({ limit: 50 }, controller.signal)
        .then((r) => r.items)
        .catch(() => [] as DocumentItem[]),
    ]).then(([subs, docs]) => {
      setSubjects(subs);
      setDocuments(docs);
    });
    return () => controller.abort();
  }, []);

  const fetchNotes = React.useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const res = await listNotes(
          {
            q: searchQuery || undefined,
            note_type: noteTypeFilter || undefined,
            subject_code: subjectFilter || undefined,
            topic_id: topicFilter || undefined,
            limit: 50,
            offset: 0,
          },
          signal,
        );
        setNotes(res.items);
        setTotal(res.total);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to load notes.",
        );
      } finally {
        setIsLoading(false);
      }
    },
    [searchQuery, noteTypeFilter, subjectFilter, topicFilter],
  );

  React.useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void fetchNotes(controller.signal);
    }, 150);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [fetchNotes]);

  const understoodCount = notes.filter((n) => Boolean(n.understood_at)).length;
  const visibleNotes = unreviewedOnly
    ? notes.filter((n) => !n.understood_at)
    : notes;
  const hasActiveFilters = Boolean(
    searchQuery || noteTypeFilter || subjectFilter || topicFilter || unreviewedOnly,
  );

  const handleClearFilters = () => {
    setSearchQuery("");
    setNoteTypeFilter("");
    setSubjectFilter("");
    setTopicFilter("");
    setUnreviewedOnly(false);
  };

  const handleGenerateNotesFromPdf = async (selection: {
    file: File | null;
    documentId: string;
  }) => {
    setPdfRunning(true);
    setPdfError(null);
    setPdfProgress(null);
    setGeneratedNoteId(null);
    try {
      const result = await runPdfToNotesPipeline({
        file: selection.file,
        documentId: selection.documentId || undefined,
        onProgress: setPdfProgress,
      });
      setGeneratedNoteId(result.notes[0]?.id ?? null);
      void fetchNotes();
      if (selection.file) {
        setDocuments((prev) =>
          prev.some((d) => d.id === result.document.id)
            ? prev
            : [result.document, ...prev],
        );
      }
    } catch (error) {
      setPdfError(
        error instanceof Error
          ? error.message
          : "Failed to generate smart notes from PDF.",
      );
    } finally {
      setPdfRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Smart Notes"
        description="Upload a PDF to generate full source-grounded study notes, revision sheets, and formulas."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/library">Open Library</Link>
          </Button>
        }
      />

      <QuickPdfDropCard
        title="PDF → Smart Notes"
        description="Drop any study PDF or choose an uploaded file. Pages, concepts, and full smart notes are created automatically in one step."
        actionLabel="Generate Full Notes"
        busyLabel="Generating Notes…"
        existingDocuments={documents}
        isRunning={pdfRunning}
        progress={pdfProgress}
        errorMessage={pdfError}
        onRun={(sel) => void handleGenerateNotesFromPdf(sel)}
        successAction={
          generatedNoteId ? (
            <Button asChild size="sm">
              <Link href={`/notes/${encodeURIComponent(generatedNoteId)}`}>
                <span>Open Generated Notes</span>
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </Button>
          ) : null
        }
      />

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>All Generated Notes</CardTitle>
              <CardDescription>
                {isLoading
                  ? "Loading notes…"
                  : `${visibleNotes.length} shown of ${total} ${total === 1 ? "note" : "notes"}${notes.length > 0 ? ` · ${understoodCount} understood` : ""}`}
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant={unreviewedOnly ? "default" : "outline"}
                size="sm"
                aria-pressed={unreviewedOnly}
                onClick={() => setUnreviewedOnly((prev) => !prev)}
              >
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                <span>To Revise Only</span>
              </Button>
              {hasActiveFilters ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleClearFilters}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Clear filters</span>
                </Button>
              ) : null}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void fetchNotes()}
                disabled={isLoading}
              >
                Refresh
              </Button>
            </div>
          </div>

          <div className="mt-2 grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="relative min-w-0">
              <Search
                className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search note title…"
                aria-label="Search notes"
                className="w-full min-w-0 max-w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            <select
              value={noteTypeFilter}
              onChange={(e) => setNoteTypeFilter(e.target.value)}
              aria-label="Filter by note type"
              className="w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">All note types</option>
              {Object.entries(NOTE_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>

            <select
              value={subjectFilter}
              onChange={(e) => setSubjectFilter(e.target.value)}
              aria-label="Filter by subject"
              className="w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">All subjects</option>
              {subjects.map((sub) => (
                <option key={sub.subject_code} value={sub.subject_code}>
                  {sub.display_name}
                </option>
              ))}
            </select>
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
          ) : isLoading && notes.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Loading notes…
            </p>
          ) : visibleNotes.length === 0 ? (
            <div className="rounded-md border border-dashed py-10 text-center">
              <BookOpen
                className="mx-auto h-8 w-8 text-muted-foreground"
                aria-hidden="true"
              />
              <p className="mt-2 text-sm font-medium">
                {hasActiveFilters
                  ? "No notes match the selected filters"
                  : "No smart notes yet"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {hasActiveFilters
                  ? "Clear active filters to view all your generated notes."
                  : "Open a processed document in My Library, extract knowledge, and click Generate Notes."}
              </p>
              {hasActiveFilters ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-4"
                  onClick={handleClearFilters}
                >
                  Clear filters
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {visibleNotes.map((note) => (
                <div
                  key={note.id}
                  className="flex flex-col justify-between rounded-lg border p-4"
                >
                  <div className="space-y-2">
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
                        <Badge variant="success" className="gap-1">
                          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                          Understood
                        </Badge>
                      ) : null}
                    </div>
                    <h3 className="font-semibold leading-snug">{note.title}</h3>
                    <p className="text-xs text-muted-foreground">
                      {note.topic_name ? `${note.topic_name} · ` : ""}v
                      {note.generation_version} ·{" "}
                      {new Date(note.created_at).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="mt-4 flex items-center justify-between gap-2">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/notes/${encodeURIComponent(note.id)}`}>
                        <span>Open Reader</span>
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                      </Link>
                    </Button>
                    <Link
                      href={`/documents/${encodeURIComponent(note.document_id)}`}
                      className="text-xs text-muted-foreground hover:text-primary hover:underline"
                    >
                      Source doc
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function SmartNotesIndexPage() {
  return (
    <React.Suspense
      fallback={
        <div className="py-10 text-center text-sm text-muted-foreground">
          Loading smart notes…
        </div>
      }
    >
      <SmartNotesContent />
    </React.Suspense>
  );
}
