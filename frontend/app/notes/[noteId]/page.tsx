"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertCircle, ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { NotesReader } from "@/components/notes/NotesReader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  getNote,
  regenerateNote,
  updateNote,
  type NoteDetailOut,
  type RegenerateNoteRequest,
} from "@/lib/api/notes";

export default function NoteReaderPage() {
  const params = useParams<{ noteId: string }>();
  const noteId = params.noteId;

  const [note, setNote] = React.useState<NoteDetailOut | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [isRegenerating, setIsRegenerating] = React.useState(false);
  const [isUpdatingUnderstood, setIsUpdatingUnderstood] = React.useState(false);

  React.useEffect(() => {
    if (!noteId) return;
    const controller = new AbortController();
    setIsLoading(true);
    setErrorMessage(null);

    getNote(noteId, controller.signal)
      .then((loaded) => setNote(loaded))
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to load note.",
        );
      })
      .finally(() => setIsLoading(false));

    return () => controller.abort();
  }, [noteId]);

  const handleRegenerate = async (payload: RegenerateNoteRequest) => {
    if (!note) return;
    setIsRegenerating(true);
    setActionError(null);
    try {
      const updated = await regenerateNote(note.id, payload);
      setNote(updated);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Failed to regenerate note.",
      );
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleToggleUnderstood = async () => {
    if (!note) return;
    setIsUpdatingUnderstood(true);
    setActionError(null);
    try {
      const updated = await updateNote(note.id, {
        understood: !note.understood_at,
      });
      setNote(updated);
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : "Failed to update note status.",
      );
    } finally {
      setIsUpdatingUnderstood(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Notes Reader"
          description="Loading smart note…"
          actions={
            <Button asChild variant="outline" size="sm">
              <Link href="/notes">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>All Notes</span>
              </Link>
            </Button>
          }
        />
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Loading note content…
          </CardContent>
        </Card>
      </div>
    );
  }

  if (errorMessage || !note) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Note Unavailable"
          description="Unable to load this note."
          actions={
            <Button asChild variant="outline" size="sm">
              <Link href="/notes">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>All Notes</span>
              </Link>
            </Button>
          }
        />
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{errorMessage ?? "Note not found."}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {actionError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{actionError}</span>
        </div>
      ) : null}

      <NotesReader
        note={note}
        isRegenerating={isRegenerating}
        isUpdatingUnderstood={isUpdatingUnderstood}
        onRegenerate={handleRegenerate}
        onToggleUnderstood={handleToggleUnderstood}
      />
    </div>
  );
}
