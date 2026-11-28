"use client";

import { AlertTriangle, CheckCircle2, FileWarning } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { CoverageAuditOut } from "@/lib/api/documents";

interface CoverageReportCardProps {
  coverage: CoverageAuditOut | null;
  isLoading: boolean;
  errorMessage: string | null;
  onInspectPagesRequiringOcr: () => void;
}

export function CoverageReportCard({
  coverage,
  isLoading,
  errorMessage,
  onInspectPagesRequiringOcr,
}: CoverageReportCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>Extraction Summary</CardTitle>
          <CardDescription>
            How much text, tables, and diagrams were extracted from your
            document. Any unreadable pages are flagged below.
          </CardDescription>
        </div>
        {coverage &&
        (coverage.pages_requiring_ocr > 0 ||
          coverage.low_confidence_pages.length > 0) ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onInspectPagesRequiringOcr}
          >
            <FileWarning className="h-4 w-4 text-amber-600" aria-hidden="true" />
            <span>Inspect Flagged Pages</span>
          </Button>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-4">
        {errorMessage ? (
          <div
            role="alert"
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
          >
            {errorMessage}
          </div>
        ) : isLoading ? (
          <p className="text-sm text-muted-foreground">
            Loading coverage audit…
          </p>
        ) : !coverage ? (
          <p className="text-sm text-muted-foreground">
            Run document processing to generate a page-level coverage report.
          </p>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div className="rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Total Pages
                </dt>
                <dd className="mt-1 text-lg font-semibold">
                  {coverage.total_pages}
                </dd>
              </div>
              <div className="rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Text Extracted
                </dt>
                <dd className="mt-1 text-lg font-semibold">
                  {coverage.pages_extracted_text}
                </dd>
              </div>
              <div className="rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Scanned / OCR Pages
                </dt>
                <dd className="mt-1 text-lg font-semibold">
                  {coverage.pages_extracted_ocr}
                </dd>
              </div>
              <div className="rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Needs OCR / Review
                </dt>
                <dd className="mt-1 text-lg font-semibold text-amber-700">
                  {coverage.pages_requiring_ocr}
                </dd>
              </div>
              <div className="rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Not Processed
                </dt>
                <dd className="mt-1 font-medium">
                  {coverage.pages_not_processed}
                </dd>
              </div>
              <div className="rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Tables Extracted
                </dt>
                <dd className="mt-1 font-medium">
                  {coverage.tables_extracted}
                </dd>
              </div>
              <div className="rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Diagrams / Images
                </dt>
                <dd className="mt-1 font-medium">
                  {coverage.images_extracted}
                </dd>
              </div>
              <div className="rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Study Sections
                </dt>
                <dd className="mt-1 font-medium">{coverage.chunks_created}</dd>
              </div>
            </dl>

            {coverage.pages_requiring_ocr > 0 ? (
              <div
                role="status"
                className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
              >
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0"
                  aria-hidden="true"
                />
                <div>
                  <p className="font-medium">
                    {coverage.pages_requiring_ocr}{" "}
                    {coverage.pages_requiring_ocr === 1 ? "page" : "pages"}{" "}
                    detected as scanned, low-text, or garbled and require OCR or
                    manual review.
                  </p>
                  <p className="mt-0.5 text-xs">
                    Open the Source Pages tab to inspect warnings or retry OCR
                    when an OCR adapter is configured.
                  </p>
                </div>
              </div>
            ) : coverage.total_pages > 0 && coverage.pages_not_processed === 0 ? (
              <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  All {coverage.total_pages} pages have extracted text
                  available for review.
                </span>
              </div>
            ) : null}

            {coverage.low_confidence_pages.length > 0 ? (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Low-Confidence / Flagged Pages
                </h4>
                <div className="flex flex-wrap gap-2">
                  {coverage.low_confidence_pages.map((p) => (
                    <Badge
                      key={p.page_number}
                      variant="warning"
                      title={p.warning ?? undefined}
                    >
                      Page {p.page_number} ({Math.round(p.confidence * 100)}%)
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
