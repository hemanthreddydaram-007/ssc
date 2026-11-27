"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { BookOpen, CheckCircle2, ExternalLink, Search, X } from "lucide-react";

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
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import { listSubjects, type SubjectOut } from "@/lib/api/knowledge";
import {
  formatNoteType,
  listNotes,
  NOTE_TYPE_LABELS,
  type NoteSummaryOut,
} from "@/lib/api/notes";

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

  React.useEffect(() => {
    const controller = new AbortController();
    listSubjects(controller.signal)
      .then(setSubjects)
      .catch(() => setSubjects([]));
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Smart Notes"
        description="Source-grounded detailed notes, quick-revision sheets, formulas, and solving strategies."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/library">Open Library</Link>
          </Button>
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
                  : `${total} ${total === 1 ? "note" : "notes"} available`}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {topicFilter ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setTopicFilter("")}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Clear topic filter</span>
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

          <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="relative">
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
                className="w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            <select
              value={noteTypeFilter}
              onChange={(e) => setNoteTypeFilter(e.target.value)}
              aria-label="Filter by note type"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
          ) : notes.length === 0 ? (
            <div className="rounded-md border border-dashed py-10 text-center">
              <BookOpen
                className="mx-auto h-8 w-8 text-muted-foreground"
                aria-hidden="true"
              />
              <p className="mt-2 text-sm font-medium">No smart notes yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Open a processed document in My Library, extract knowledge, and
                click Generate Notes.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {notes.map((note) => (
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
