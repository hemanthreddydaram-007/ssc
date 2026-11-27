"use client";

import * as React from "react";

import { DocumentTable } from "@/components/documents/DocumentTable";
import { UploadPanel } from "@/components/documents/UploadPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  deleteDocument,
  listDocuments,
  type DocumentItem,
} from "@/lib/api/documents";
import { listExamConfigs, type ExamConfig } from "@/lib/api/examConfigs";

export default function LibraryPage() {
  const [examConfigs, setExamConfigs] = React.useState<ExamConfig[]>([]);
  const [examConfigsLoading, setExamConfigsLoading] = React.useState(true);

  const [documents, setDocuments] = React.useState<DocumentItem[]>([]);
  const [total, setTotal] = React.useState(0);
  const [isLoadingDocs, setIsLoadingDocs] = React.useState(true);
  const [docsError, setDocsError] = React.useState<string | null>(null);

  const [searchQuery, setSearchQuery] = React.useState("");
  const [materialTypeFilter, setMaterialTypeFilter] = React.useState("");

  React.useEffect(() => {
    const controller = new AbortController();
    setExamConfigsLoading(true);
    listExamConfigs(controller.signal)
      .then((configs) => setExamConfigs(configs))
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setExamConfigs([]);
      })
      .finally(() => setExamConfigsLoading(false));
    return () => controller.abort();
  }, []);

  const fetchDocuments = React.useCallback(
    async (signal?: AbortSignal) => {
      setIsLoadingDocs(true);
      setDocsError(null);
      try {
        const res = await listDocuments(
          {
            q: searchQuery || undefined,
            material_type: materialTypeFilter || undefined,
            limit: 50,
            offset: 0,
          },
          signal,
        );
        setDocuments(res.items);
        setTotal(res.total);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setDocsError(
          error instanceof Error
            ? error.message
            : "Failed to load documents from backend.",
        );
      } finally {
        setIsLoadingDocs(false);
      }
    },
    [searchQuery, materialTypeFilter],
  );

  React.useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void fetchDocuments(controller.signal);
    }, 150);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [fetchDocuments]);

  const handleDelete = async (documentId: string) => {
    setDocsError(null);
    try {
      await deleteDocument(documentId, true);
      await fetchDocuments();
    } catch (error) {
      setDocsError(
        error instanceof Error ? error.message : "Failed to delete document.",
      );
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Library"
        description="Upload study PDFs, images, or pasted text and manage your private study materials."
      />

      <UploadPanel
        examConfigs={examConfigs}
        examConfigsLoading={examConfigsLoading}
        onDocumentCreated={() => void fetchDocuments()}
      />

      <DocumentTable
        documents={documents}
        total={total}
        isLoading={isLoadingDocs}
        errorMessage={docsError}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        materialTypeFilter={materialTypeFilter}
        onMaterialTypeFilterChange={setMaterialTypeFilter}
        onDelete={handleDelete}
        onRefresh={() => void fetchDocuments()}
      />
    </div>
  );
}
