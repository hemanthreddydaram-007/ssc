import Link from "next/link";
import { FileText } from "lucide-react";

import type { NoteSourceRef } from "@/lib/api/notes";

interface SourceCitationLinkProps {
  refs: readonly NoteSourceRef[];
  fallbackDocumentId: string;
}

export function SourceCitationLink({
  refs,
  fallbackDocumentId,
}: SourceCitationLinkProps) {
  if (refs.length === 0) {
    return null;
  }

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {refs.map((ref, idx) => {
        const docId = ref.document_id || fallbackDocumentId;
        const pageLabel =
          ref.page_number !== null && ref.page_number !== undefined
            ? `Page ${ref.page_number}`
            : "Source page";
        const href =
          ref.page_number !== null && ref.page_number !== undefined
            ? `/documents/${encodeURIComponent(docId)}?tab=source_pages&page=${ref.page_number}`
            : `/documents/${encodeURIComponent(docId)}?tab=source_pages`;

        return (
          <Link
            key={`${docId}-${ref.page_number ?? "none"}-${idx}`}
            href={href}
            title={ref.supporting_excerpt ?? undefined}
            className="inline-flex items-center gap-1.5 rounded border bg-muted/60 px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <FileText className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>{pageLabel}</span>
            {ref.supporting_excerpt ? (
              <span className="hidden max-w-[220px] truncate italic sm:inline">
                &ldquo;{ref.supporting_excerpt}&rdquo;
              </span>
            ) : null}
          </Link>
        );
      })}
    </div>
  );
}
