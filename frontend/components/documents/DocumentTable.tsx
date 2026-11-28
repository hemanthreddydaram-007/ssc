"use client";

import * as React from "react";
import Link from "next/link";
import { ExternalLink, Search, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  MATERIAL_TYPE_OPTIONS,
  formatBytes,
  type DocumentItem,
} from "@/lib/api/documents";
import { formatSubjectLabel } from "@/lib/api/examConfigs";

interface DocumentTableProps {
  documents: readonly DocumentItem[];
  total: number;
  isLoading: boolean;
  errorMessage: string | null;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  materialTypeFilter: string;
  onMaterialTypeFilterChange: (value: string) => void;
  onDelete: (documentId: string) => Promise<void>;
  onRefresh: () => void;
}

function getStatusBadgeVariant(
  status: string,
): "success" | "warning" | "destructive" | "secondary" {
  switch (status) {
    case "ready":
    case "completed":
      return "success";
    case "processing":
    case "queued":
      return "warning";
    case "failed":
      return "destructive";
    default:
      return "secondary";
  }
}

export function DocumentTable({
  documents,
  total,
  isLoading,
  errorMessage,
  searchQuery,
  onSearchQueryChange,
  materialTypeFilter,
  onMaterialTypeFilterChange,
  onDelete,
  onRefresh,
}: DocumentTableProps) {
  const [confirmDeleteId, setConfirmDeleteId] = React.useState<string | null>(
    null,
  );
  const [deletingId, setDeletingId] = React.useState<string | null>(null);

  const handleConfirmDelete = async (documentId: string) => {
    setDeletingId(documentId);
    try {
      await onDelete(documentId);
      setConfirmDeleteId(null);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Document Library</CardTitle>
            <CardDescription>
              {isLoading
                ? "Loading uploaded materials…"
                : `${total} ${total === 1 ? "document" : "documents"} stored in your private library`}
            </CardDescription>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={isLoading}
          >
            Refresh
          </Button>
        </div>

        <div className="mt-2 grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="relative min-w-0 sm:col-span-2">
            <Search
              className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
              aria-hidden="true"
            />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => onSearchQueryChange(e.target.value)}
              placeholder="Search by document title or filename…"
              aria-label="Search documents"
              className="w-full min-w-0 max-w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <select
            value={materialTypeFilter}
            onChange={(e) => onMaterialTypeFilterChange(e.target.value)}
            aria-label="Filter by material type"
            className="w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="">All material types</option>
            {MATERIAL_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </CardHeader>

      <CardContent className="min-w-0">
        {errorMessage ? (
          <div
            role="alert"
            className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          >
            {errorMessage}
          </div>
        ) : isLoading && documents.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Loading library…
          </p>
        ) : documents.length === 0 ? (
          <div className="rounded-md border border-dashed py-10 text-center">
            <p className="text-sm font-medium">No documents found</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Upload a PDF, image, or pasted text above to build your library.
            </p>
          </div>
        ) : (
          <>
            {/* Mobile card list (prevents horizontal clipping on 390px viewports) */}
            <div className="space-y-3 md:hidden">
              {documents.map((doc) => {
                const isConfirming = confirmDeleteId === doc.id;
                const isDeleting = deletingId === doc.id;
                const effectiveSubject =
                  doc.subject_code ?? doc.detected_subject_code;
                const uploadedAtLabel = new Date(doc.created_at).toLocaleString(
                  [],
                  { dateStyle: "medium", timeStyle: "short" },
                );

                return (
                  <div
                    key={doc.id}
                    className="space-y-2.5 rounded-lg border p-3.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <Link
                          href={`/documents/${doc.id}`}
                          className="break-words text-sm font-medium text-foreground hover:text-primary hover:underline"
                        >
                          {doc.title}
                        </Link>
                        <p className="mt-0.5 break-all text-xs text-muted-foreground">
                          {doc.original_filename} · {uploadedAtLabel}
                        </p>
                      </div>
                      <Badge
                        variant={getStatusBadgeVariant(doc.status)}
                        className="shrink-0"
                      >
                        {doc.status}
                      </Badge>
                    </div>

                    <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                      <span className="rounded bg-muted px-2 py-0.5">
                        {effectiveSubject
                          ? formatSubjectLabel(effectiveSubject)
                          : "Auto-detect"}
                      </span>
                      <span className="rounded bg-muted px-2 py-0.5 capitalize">
                        {doc.material_type.replace(/_/g, " ")}
                      </span>
                      <span className="rounded bg-muted px-2 py-0.5">
                        {doc.page_count}{" "}
                        {doc.page_count === 1 ? "page" : "pages"}
                      </span>
                      <span className="rounded bg-muted px-2 py-0.5">
                        {formatBytes(doc.file_size_bytes)}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                      {isConfirming ? (
                        <>
                          <Button
                            type="button"
                            size="sm"
                            variant="destructive"
                            disabled={isDeleting}
                            onClick={() => void handleConfirmDelete(doc.id)}
                          >
                            {isDeleting ? "Deleting…" : "Confirm"}
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={isDeleting}
                            onClick={() => setConfirmDeleteId(null)}
                          >
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button asChild size="sm" variant="outline">
                            <Link href={`/documents/${doc.id}`}>
                              <span>Open</span>
                              <ExternalLink
                                className="h-3.5 w-3.5"
                                aria-hidden="true"
                              />
                            </Link>
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            aria-label={`Delete ${doc.title}`}
                            onClick={() => setConfirmDeleteId(doc.id)}
                          >
                            <Trash2
                              className="h-4 w-4 text-destructive"
                              aria-hidden="true"
                            />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Desktop / Tablet table */}
            <div className="hidden min-w-0 overflow-x-auto md:block">
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="py-3 pr-4 font-medium">Document</th>
                    <th className="px-3 py-3 font-medium">Subject</th>
                    <th className="px-3 py-3 font-medium">Type</th>
                    <th className="px-3 py-3 font-medium">Pages</th>
                    <th className="px-3 py-3 font-medium">Size</th>
                    <th className="px-3 py-3 font-medium">Status</th>
                    <th className="py-3 pl-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {documents.map((doc) => {
                    const isConfirming = confirmDeleteId === doc.id;
                    const isDeleting = deletingId === doc.id;
                    const effectiveSubject =
                      doc.subject_code ?? doc.detected_subject_code;
                    const uploadedAtLabel = new Date(
                      doc.created_at,
                    ).toLocaleString([], {
                      dateStyle: "medium",
                      timeStyle: "short",
                    });

                    return (
                      <tr key={doc.id} className="hover:bg-muted/30">
                        <td className="max-w-[260px] py-3 pr-4">
                          <Link
                            href={`/documents/${doc.id}`}
                            className="break-words font-medium text-foreground hover:text-primary hover:underline"
                          >
                            {doc.title}
                          </Link>
                          <p className="mt-0.5 truncate text-xs text-muted-foreground">
                            {doc.original_filename} · {uploadedAtLabel}
                          </p>
                        </td>
                        <td className="px-3 py-3 text-xs">
                          {effectiveSubject
                            ? formatSubjectLabel(effectiveSubject)
                            : "Auto-detect"}
                        </td>
                        <td className="px-3 py-3 text-xs capitalize">
                          {doc.material_type.replace(/_/g, " ")}
                        </td>
                        <td className="whitespace-nowrap px-3 py-3 text-xs">
                          {doc.page_count}{" "}
                          {doc.page_count === 1 ? "page" : "pages"}
                        </td>
                        <td className="whitespace-nowrap px-3 py-3 text-xs">
                          {formatBytes(doc.file_size_bytes)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-3">
                          <Badge variant={getStatusBadgeVariant(doc.status)}>
                            {doc.status}
                          </Badge>
                        </td>
                        <td className="whitespace-nowrap py-3 pl-3 text-right">
                          {isConfirming ? (
                            <div className="inline-flex items-center gap-1.5">
                              <Button
                                type="button"
                                size="sm"
                                variant="destructive"
                                disabled={isDeleting}
                                onClick={() => void handleConfirmDelete(doc.id)}
                              >
                                {isDeleting ? "Deleting…" : "Confirm"}
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                disabled={isDeleting}
                                onClick={() => setConfirmDeleteId(null)}
                              >
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <div className="inline-flex shrink-0 items-center gap-1.5">
                              <Button asChild size="sm" variant="outline">
                                <Link href={`/documents/${doc.id}`}>
                                  <span>Open</span>
                                  <ExternalLink
                                    className="h-3.5 w-3.5"
                                    aria-hidden="true"
                                  />
                                </Link>
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                aria-label={`Delete ${doc.title}`}
                                onClick={() => setConfirmDeleteId(doc.id)}
                              >
                                <Trash2
                                  className="h-4 w-4 text-destructive"
                                  aria-hidden="true"
                                />
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
