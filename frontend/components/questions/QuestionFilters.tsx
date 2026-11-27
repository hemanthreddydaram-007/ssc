"use client";

import { Search } from "lucide-react";

import type { DocumentItem } from "@/lib/api/documents";
import type { SubjectOut, TopicSummaryOut } from "@/lib/api/knowledge";

export interface QuestionFilterState {
  q: string;
  subject_code: string;
  topic_id: string;
  difficulty: string;
  origin: string;
  validation_status: string;
  document_id: string;
}

interface QuestionFiltersProps {
  filters: QuestionFilterState;
  onChange: (next: QuestionFilterState) => void;
  subjects: readonly SubjectOut[];
  topics: readonly TopicSummaryOut[];
  documents?: readonly DocumentItem[];
  hideDocumentFilter?: boolean;
}

export function QuestionFilters({
  filters,
  onChange,
  subjects,
  topics,
  documents = [],
  hideDocumentFilter = false,
}: QuestionFiltersProps) {
  const update = (patch: Partial<QuestionFilterState>) => {
    onChange({ ...filters, ...patch });
  };

  const filteredTopics = filters.subject_code
    ? topics.filter((t) => t.subject_code === filters.subject_code)
    : topics;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="relative sm:col-span-2">
        <Search
          className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          type="search"
          value={filters.q}
          onChange={(e) => update({ q: e.target.value })}
          placeholder="Search question text…"
          aria-label="Search questions"
          className="w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      <select
        value={filters.subject_code}
        onChange={(e) =>
          update({ subject_code: e.target.value, topic_id: "" })
        }
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

      <select
        value={filters.topic_id}
        onChange={(e) => update({ topic_id: e.target.value })}
        aria-label="Filter by topic"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">All topics</option>
        {filteredTopics.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {topic.name}
          </option>
        ))}
      </select>

      <select
        value={filters.difficulty}
        onChange={(e) => update({ difficulty: e.target.value })}
        aria-label="Filter by difficulty"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">All difficulties</option>
        <option value="easy">Easy</option>
        <option value="medium">Medium</option>
        <option value="hard">Hard</option>
      </select>

      <select
        value={filters.origin}
        onChange={(e) => update({ origin: e.target.value })}
        aria-label="Filter by source origin"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">All origins</option>
        <option value="extracted">Extracted from source</option>
        <option value="generated">AI generated</option>
        <option value="manual">Manual / Imported</option>
      </select>

      <select
        value={filters.validation_status}
        onChange={(e) => update({ validation_status: e.target.value })}
        aria-label="Filter by validation status"
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">All validation statuses</option>
        <option value="verified">Verified</option>
        <option value="needs_review">Needs review</option>
        <option value="rejected">Rejected</option>
      </select>

      {!hideDocumentFilter ? (
        <select
          value={filters.document_id}
          onChange={(e) => update({ document_id: e.target.value })}
          aria-label="Filter by document"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">All documents</option>
          {documents.map((doc) => (
            <option key={doc.id} value={doc.id}>
              {doc.title}
            </option>
          ))}
        </select>
      ) : null}
    </div>
  );
}
