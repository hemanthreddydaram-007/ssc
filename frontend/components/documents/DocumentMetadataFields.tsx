"use client";

import * as React from "react";

import {
  LANGUAGE_OPTIONS,
  MATERIAL_TYPE_OPTIONS,
} from "@/lib/api/documents";
import {
  formatSubjectLabel,
  type ExamConfig,
} from "@/lib/api/examConfigs";

export interface MetadataFormValues {
  title: string;
  exam_config_id: string;
  subject_code: string;
  material_type: string;
  language: string;
  chapter_or_topic_hint: string;
  source_label: string;
}

interface DocumentMetadataFieldsProps {
  values: MetadataFormValues;
  onChange: (next: MetadataFormValues) => void;
  examConfigs: readonly ExamConfig[];
  examConfigsLoading?: boolean;
  titleRequired?: boolean;
  titlePlaceholder?: string;
  disabled?: boolean;
  idPrefix?: string;
}

const DEFAULT_SUBJECT_CODES = [
  "quantitative_aptitude",
  "reasoning",
  "english",
  "general_awareness",
] as const;

export function DocumentMetadataFields({
  values,
  onChange,
  examConfigs,
  examConfigsLoading = false,
  titleRequired = false,
  titlePlaceholder = "Optional — defaults to filename",
  disabled = false,
  idPrefix = "doc-meta",
}: DocumentMetadataFieldsProps) {
  const selectedExam = examConfigs.find((c) => c.id === values.exam_config_id);
  const subjectCodes: readonly string[] =
    selectedExam?.config_json.subjects &&
    selectedExam.config_json.subjects.length > 0
      ? selectedExam.config_json.subjects
      : DEFAULT_SUBJECT_CODES;

  const update = (patch: Partial<MetadataFormValues>) => {
    onChange({ ...values, ...patch });
  };

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <label
          htmlFor={`${idPrefix}-title`}
          className="block text-sm font-medium"
        >
          Title {titleRequired ? <span className="text-destructive">*</span> : null}
        </label>
        <input
          id={`${idPrefix}-title`}
          type="text"
          value={values.title}
          onChange={(e) => update({ title: e.target.value })}
          required={titleRequired}
          disabled={disabled}
          placeholder={titlePlaceholder}
          className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        />
      </div>

      <div>
        <label
          htmlFor={`${idPrefix}-exam`}
          className="block text-sm font-medium"
        >
          Exam
        </label>
        <select
          id={`${idPrefix}-exam`}
          value={values.exam_config_id}
          onChange={(e) => update({ exam_config_id: e.target.value })}
          disabled={disabled || examConfigsLoading}
          className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          <option value="">Not specified / General</option>
          {examConfigs.map((cfg) => (
            <option key={cfg.id} value={cfg.id}>
              {cfg.name} (v{cfg.version})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor={`${idPrefix}-subject`}
          className="block text-sm font-medium"
        >
          Subject
        </label>
        <select
          id={`${idPrefix}-subject`}
          value={values.subject_code}
          onChange={(e) => update({ subject_code: e.target.value })}
          disabled={disabled}
          className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          <option value="">Auto-detect (classify during processing)</option>
          {subjectCodes.map((code) => (
            <option key={code} value={code}>
              {formatSubjectLabel(code)}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor={`${idPrefix}-material-type`}
          className="block text-sm font-medium"
        >
          Material Type
        </label>
        <select
          id={`${idPrefix}-material-type`}
          value={values.material_type}
          onChange={(e) => update({ material_type: e.target.value })}
          disabled={disabled}
          className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          {MATERIAL_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor={`${idPrefix}-language`}
          className="block text-sm font-medium"
        >
          Language
        </label>
        <select
          id={`${idPrefix}-language`}
          value={values.language}
          onChange={(e) => update({ language: e.target.value })}
          disabled={disabled}
          className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor={`${idPrefix}-chapter`}
          className="block text-sm font-medium"
        >
          Chapter / Topic <span className="text-xs text-muted-foreground">(optional)</span>
        </label>
        <input
          id={`${idPrefix}-chapter`}
          type="text"
          value={values.chapter_or_topic_hint}
          onChange={(e) => update({ chapter_or_topic_hint: e.target.value })}
          disabled={disabled}
          placeholder="e.g. Time and Work"
          className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        />
      </div>

      <div>
        <label
          htmlFor={`${idPrefix}-source-label`}
          className="block text-sm font-medium"
        >
          Source / Label <span className="text-xs text-muted-foreground">(optional)</span>
        </label>
        <input
          id={`${idPrefix}-source-label`}
          type="text"
          value={values.source_label}
          onChange={(e) => update({ source_label: e.target.value })}
          disabled={disabled}
          placeholder="e.g. SSC CHSL 2024 Tier 1 Shift 1"
          className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        />
      </div>
    </div>
  );
}
