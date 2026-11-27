"use client";

import * as React from "react";
import { AlertTriangle, FileText, Image as ImageIcon, Table2 } from "lucide-react";

import { AuthAssetImage } from "@/components/common/AuthAssetImage";
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
  type DocumentAssetOut,
  type DocumentPageOut,
} from "@/lib/api/documents";

interface PageReviewListProps {
  documentId: string;
  pages: readonly DocumentPageOut[];
  isLoading: boolean;
  errorMessage: string | null;
  needsOcrOnly: boolean;
  onNeedsOcrOnlyChange: (next: boolean) => void;
  onRefresh: () => void;
}

function TablePreview({ rawTable, index }: { rawTable: unknown; index: number }) {
  if (!Array.isArray(rawTable) || rawTable.length === 0) {
    return null;
  }

  const rows = rawTable.filter((row): row is unknown[] => Array.isArray(row));
  if (rows.length === 0) {
    return (
      <pre className="overflow-x-auto rounded bg-muted p-2 text-xs">
        {JSON.stringify(rawTable, null, 2)}
      </pre>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <div className="border-b bg-muted/50 px-3 py-1.5 text-xs font-medium text-muted-foreground">
        Table {index + 1}
      </div>
      <table className="w-full border-collapse text-left text-xs">
        <tbody>
          {rows.map((row, rIdx) => (
            <tr key={rIdx} className="border-b last:border-b-0">
              {row.map((cell, cIdx) => (
                <td
                  key={cIdx}
                  className="border-r px-2.5 py-1.5 align-top last:border-r-0"
                >
                  {cell === null || cell === undefined ? "" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AssetThumbnail({
  documentId,
  asset,
}: {
  documentId: string;
  asset: DocumentAssetOut;
}) {
  return (
    <div className="overflow-hidden rounded-md border bg-muted/20">
      <div className="flex items-center justify-between border-b bg-muted/40 px-2.5 py-1 text-xs text-muted-foreground">
        <span className="capitalize">{asset.asset_type.replace(/_/g, " ")}</span>
        <span>
          {asset.width}×{asset.height}
        </span>
      </div>
      <div className="p-2">
        <AuthAssetImage
          documentId={documentId}
          assetId={asset.id}
          alt={`Extracted ${asset.asset_type} on page ${asset.page_number}`}
          className="mx-auto max-h-48 w-auto rounded object-contain"
        />
      </div>
    </div>
  );
}

export function PageReviewList({
  documentId,
  pages,
  isLoading,
  errorMessage,
  needsOcrOnly,
  onNeedsOcrOnlyChange,
  onRefresh,
}: PageReviewListProps) {
  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle>Source Pages Review</CardTitle>
          <CardDescription>
            Inspect extracted text, tables, diagrams, and OCR warnings page by
            page without calling the LLM.
          </CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={needsOcrOnly ? "default" : "outline"}
            size="sm"
            onClick={() => onNeedsOcrOnlyChange(!needsOcrOnly)}
          >
            {needsOcrOnly ? "Showing OCR / Flagged Only" : "Filter: Needs OCR"}
          </Button>
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
          <p className="py-8 text-center text-sm text-muted-foreground">
            Loading extracted pages…
          </p>
        ) : pages.length === 0 ? (
          <div className="rounded-md border border-dashed py-10 text-center">
            <p className="text-sm font-medium">
              {needsOcrOnly
                ? "No pages flagged for OCR"
                : "No extracted pages yet"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {needsOcrOnly
                ? "Switch off the filter to view all extracted pages."
                : "Click Process Document above to run page-level extraction."}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {pages.map((page) => (
              <div
                key={page.id}
                className="rounded-lg border bg-card p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                      <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
                      Page {page.page_number}
                    </span>
                    <Badge variant="outline">{page.extraction_method}</Badge>
                    <Badge
                      variant={page.needs_ocr ? "warning" : "success"}
                    >
                      {page.needs_ocr ? "Needs OCR / Review" : page.processing_status}
                    </Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span>Confidence: {Math.round(page.confidence * 100)}%</span>
                    <span>{page.raw_char_count} chars</span>
                    {page.table_count > 0 ? (
                      <span className="inline-flex items-center gap-1">
                        <Table2 className="h-3.5 w-3.5" aria-hidden="true" />
                        {page.table_count}
                      </span>
                    ) : null}
                    {page.assets.length > 0 ? (
                      <span className="inline-flex items-center gap-1">
                        <ImageIcon className="h-3.5 w-3.5" aria-hidden="true" />
                        {page.assets.length}
                      </span>
                    ) : null}
                  </div>
                </div>

                {page.warning ? (
                  <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-900">
                    <AlertTriangle
                      className="mt-0.5 h-3.5 w-3.5 shrink-0"
                      aria-hidden="true"
                    />
                    <span>{page.warning}</span>
                  </div>
                ) : null}

                <div className="mt-3">
                  {page.extracted_text.trim().length > 0 ? (
                    <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-sans text-xs leading-relaxed">
                      {page.extracted_text}
                    </pre>
                  ) : (
                    <p className="rounded-md border border-dashed p-3 text-xs italic text-muted-foreground">
                      No selectable text extracted on this page.
                    </p>
                  )}
                </div>

                {page.tables_json && page.tables_json.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {page.tables_json.map((tbl, idx) => (
                      <TablePreview key={idx} rawTable={tbl} index={idx} />
                    ))}
                  </div>
                ) : null}

                {page.assets.length > 0 ? (
                  <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {page.assets.map((asset) => (
                      <AssetThumbnail
                        key={asset.id}
                        documentId={documentId}
                        asset={asset}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
