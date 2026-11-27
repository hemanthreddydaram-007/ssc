"use client";

import * as React from "react";
import {
  AlertCircle,
  AlertTriangle,
  BookMarked,
  Check,
  CheckCircle2,
  Edit3,
  Layers,
  Sparkles,
  X,
} from "lucide-react";

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
  LANGUAGE_OPTIONS,
  MATERIAL_TYPE_OPTIONS,
  type DocumentItem,
} from "@/lib/api/documents";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import type {
  DocumentKnowledgeOut,
  FactOut,
  SubjectOut,
} from "@/lib/api/knowledge";

interface KnowledgePanelProps {
  document: DocumentItem;
  knowledge: DocumentKnowledgeOut | null;
  subjects: readonly SubjectOut[];
  isLoading: boolean;
  errorMessage: string | null;
  hasExtractedPages: boolean;
  isStartingExtract: boolean;
  isJobPolling: boolean;
  onExtractKnowledge: (forceReprocess: boolean) => void;
  onOverrideClassification: (payload: {
    subject_code: string | null;
    material_type: string;
    language: string;
  }) => Promise<void>;
  onUpdateFact: (
    factId: string,
    payload: { content?: string; review_status?: string },
  ) => Promise<void>;
  onRefresh: () => void;
}

function getProvenanceBadge(provenance: string) {
  switch (provenance.toLowerCase()) {
    case "extracted":
      return <Badge variant="success">Extracted</Badge>;
    case "paraphrased":
      return <Badge variant="secondary">Paraphrased</Badge>;
    case "ai_explanation":
      return <Badge variant="outline">AI explanation</Badge>;
    case "unverified":
    default:
      return <Badge variant="warning">Unverified</Badge>;
  }
}

function getReviewBadge(reviewStatus: string, hasConflict: boolean) {
  if (hasConflict || reviewStatus === "conflict") {
    return <Badge variant="destructive">Conflict</Badge>;
  }
  switch (reviewStatus.toLowerCase()) {
    case "verified":
      return <Badge variant="success">Verified</Badge>;
    case "rejected":
    case "failed_review":
      return <Badge variant="destructive">{reviewStatus.replace(/_/g, " ")}</Badge>;
    default:
      return <Badge variant="warning">Needs review</Badge>;
  }
}

export function KnowledgePanel({
  document,
  knowledge,
  subjects,
  isLoading,
  errorMessage,
  hasExtractedPages,
  isStartingExtract,
  isJobPolling,
  onExtractKnowledge,
  onOverrideClassification,
  onUpdateFact,
  onRefresh,
}: KnowledgePanelProps) {
  const [selectedSubject, setSelectedSubject] = React.useState(
    document.subject_code ?? document.detected_subject_code ?? "",
  );
  const [selectedMaterialType, setSelectedMaterialType] = React.useState(
    document.material_type,
  );
  const [selectedLanguage, setSelectedLanguage] = React.useState(
    document.language,
  );
  const [isSavingClassification, setIsSavingClassification] =
    React.useState(false);
  const [classificationMsg, setClassificationMsg] = React.useState<
    string | null
  >(null);

  const [editingFactId, setEditingFactId] = React.useState<string | null>(null);
  const [editingContent, setEditingContent] = React.useState("");
  const [savingFactId, setSavingFactId] = React.useState<string | null>(null);

  React.useEffect(() => {
    setSelectedSubject(
      document.subject_code ?? document.detected_subject_code ?? "",
    );
    setSelectedMaterialType(document.material_type);
    setSelectedLanguage(document.language);
  }, [
    document.subject_code,
    document.detected_subject_code,
    document.material_type,
    document.language,
  ]);

  const subjectOptions: readonly { code: string; label: string }[] =
    subjects.length > 0
      ? subjects.map((s) => ({
          code: s.subject_code,
          label: s.display_name,
        }))
      : [
          { code: "quantitative_aptitude", label: "Quantitative Aptitude / Maths" },
          { code: "reasoning", label: "General Intelligence / Reasoning" },
          { code: "english", label: "English Language" },
          { code: "general_awareness", label: "General Awareness" },
          { code: "unknown", label: "Unknown / Mixed" },
        ];

  const handleSaveClassification = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSavingClassification(true);
    setClassificationMsg(null);
    try {
      await onOverrideClassification({
        subject_code: selectedSubject || null,
        material_type: selectedMaterialType,
        language: selectedLanguage,
      });
      setClassificationMsg("Classification saved.");
    } finally {
      setIsSavingClassification(false);
    }
  };

  const handleFactAction = async (
    fact: FactOut,
    payload: { content?: string; review_status?: string },
  ) => {
    setSavingFactId(fact.id);
    try {
      await onUpdateFact(fact.id, payload);
      if (payload.content !== undefined) {
        setEditingFactId(null);
      }
    } finally {
      setSavingFactId(null);
    }
  };

  const topicsMap = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const topic of knowledge?.topics ?? []) {
      map.set(topic.id, topic.name);
    }
    return map;
  }, [knowledge?.topics]);

  const hasKnowledge =
    (knowledge?.topics.length ?? 0) > 0 ||
    (knowledge?.concepts.length ?? 0) > 0 ||
    (knowledge?.facts.length ?? 0) > 0;

  return (
    <div className="space-y-6">
      {/* Classification & Trigger Card */}
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
              <CardTitle>Structured Knowledge &amp; Classification</CardTitle>
              {document.detected_subject_code ? (
                <Badge variant="outline">
                  AI detected:{" "}
                  {formatSubjectLabel(document.detected_subject_code)}
                  {document.classification_confidence !== null
                    ? ` (${Math.round(document.classification_confidence * 100)}%)`
                    : ""}
                </Badge>
              ) : null}
            </div>
            <CardDescription>
              Extract topics, concepts, formulas, facts, and question
              candidates with page-level provenance.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              disabled={!hasExtractedPages || isStartingExtract || isJobPolling}
              onClick={() => onExtractKnowledge(hasKnowledge)}
            >
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              <span>
                {isStartingExtract
                  ? "Starting…"
                  : isJobPolling
                    ? "Extracting…"
                    : hasKnowledge
                      ? "Re-extract Knowledge"
                      : "Extract Knowledge"}
              </span>
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
          {!hasExtractedPages ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0"
                aria-hidden="true"
              />
              <span>
                Run <strong>Process Document</strong> first to extract pages and
                semantic chunks before extracting knowledge.
              </span>
            </div>
          ) : null}

          <form
            onSubmit={handleSaveClassification}
            className="grid grid-cols-1 gap-3 rounded-md border bg-muted/30 p-4 sm:grid-cols-4 sm:items-end"
          >
            <div>
              <label
                htmlFor="classification-subject"
                className="block text-xs font-medium text-muted-foreground"
              >
                Subject Classification
              </label>
              <select
                id="classification-subject"
                value={selectedSubject}
                onChange={(e) => {
                  setSelectedSubject(e.target.value);
                  setClassificationMsg(null);
                }}
                disabled={isSavingClassification}
                className="mt-1 w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">Unassigned / Auto</option>
                {subjectOptions.map((opt) => (
                  <option key={opt.code} value={opt.code}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="classification-material"
                className="block text-xs font-medium text-muted-foreground"
              >
                Material Type
              </label>
              <select
                id="classification-material"
                value={selectedMaterialType}
                onChange={(e) => {
                  setSelectedMaterialType(e.target.value);
                  setClassificationMsg(null);
                }}
                disabled={isSavingClassification}
                className="mt-1 w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
                htmlFor="classification-language"
                className="block text-xs font-medium text-muted-foreground"
              >
                Language
              </label>
              <select
                id="classification-language"
                value={selectedLanguage}
                onChange={(e) => {
                  setSelectedLanguage(e.target.value);
                  setClassificationMsg(null);
                }}
                disabled={isSavingClassification}
                className="mt-1 w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {LANGUAGE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="submit"
                variant="outline"
                size="sm"
                disabled={isSavingClassification}
              >
                {isSavingClassification ? "Saving…" : "Override Classification"}
              </Button>
              {classificationMsg ? (
                <span className="text-xs text-emerald-700">
                  {classificationMsg}
                </span>
              ) : null}
            </div>
          </form>

          {errorMessage ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
            >
              <AlertCircle
                className="mt-0.5 h-4 w-4 shrink-0"
                aria-hidden="true"
              />
              <span>{errorMessage}</span>
            </div>
          ) : null}

          {knowledge && knowledge.rejected_or_uncertain_count > 0 ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0"
                aria-hidden="true"
              />
              <span>
                {knowledge.rejected_or_uncertain_count} extracted{" "}
                {knowledge.rejected_or_uncertain_count === 1 ? "item" : "items"}{" "}
                flagged as uncertain, ungrounded, or conflicting and require
                review before relying on them.
              </span>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {isLoading && !knowledge ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading extracted knowledge…
          </CardContent>
        </Card>
      ) : knowledge ? (
        <>
          {/* Detected Topics */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-primary" aria-hidden="true" />
                <CardTitle>Detected Topics ({knowledge.topics.length})</CardTitle>
              </div>
              <CardDescription>
                Topics mapped from this document; unknown topics remain
                explicitly marked rather than forced into a wrong category.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {knowledge.topics.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No topics extracted yet.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {knowledge.topics.map((topic) => (
                    <div
                      key={topic.id}
                      className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-1.5 text-sm"
                    >
                      <span className="font-medium">{topic.name}</span>
                      <Badge variant="outline" className="text-[11px]">
                        {formatSubjectLabel(topic.subject_code)}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Concepts */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <BookMarked
                  className="h-4 w-4 text-primary"
                  aria-hidden="true"
                />
                <CardTitle>
                  Extracted Concepts ({knowledge.concepts.length})
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {knowledge.concepts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No concepts extracted yet.
                </p>
              ) : (
                <div className="space-y-3">
                  {knowledge.concepts.map((concept) => {
                    const topicName = concept.topic_id
                      ? topicsMap.get(concept.topic_id)
                      : null;
                    return (
                      <div
                        key={concept.id}
                        className="rounded-md border p-4 space-y-2"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h4 className="font-semibold">{concept.title}</h4>
                          <div className="flex flex-wrap items-center gap-1.5">
                            {topicName ? (
                              <Badge variant="outline">{topicName}</Badge>
                            ) : null}
                            {getProvenanceBadge(concept.provenance)}
                            {getReviewBadge(concept.review_status, false)}
                          </div>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {concept.explanation}
                        </p>
                        {concept.source_refs_json &&
                        concept.source_refs_json.length > 0 ? (
                          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                            {concept.source_refs_json.map((ref, idx) => (
                              <span
                                key={idx}
                                className="rounded bg-muted px-2 py-0.5"
                              >
                                {ref.page_number
                                  ? `Page ${ref.page_number}`
                                  : "Source ref"}
                                {ref.supporting_excerpt
                                  ? `: "${ref.supporting_excerpt.slice(0, 90)}${ref.supporting_excerpt.length > 90 ? "…" : ""}"`
                                  : ""}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Facts & Formulas with Inline Review */}
          <Card>
            <CardHeader>
              <CardTitle>
                Facts, Rules &amp; Formulas ({knowledge.facts.length})
              </CardTitle>
              <CardDescription>
                Every fact retains its provenance, page reference, and review
                status. Conflicting values are flagged separately rather than
                merged.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {knowledge.facts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No facts or formulas extracted yet.
                </p>
              ) : (
                <div className="space-y-3">
                  {knowledge.facts.map((fact) => {
                    const hasConflict = Boolean(fact.conflict_group_id);
                    const isEditing = editingFactId === fact.id;
                    const isBusy = savingFactId === fact.id;
                    const topicName = fact.topic_id
                      ? topicsMap.get(fact.topic_id)
                      : null;

                    return (
                      <div
                        key={fact.id}
                        className="rounded-md border p-4 space-y-2.5"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge variant="outline" className="capitalize">
                              {fact.fact_type.replace(/_/g, " ")}
                            </Badge>
                            {topicName ? (
                              <Badge variant="outline">{topicName}</Badge>
                            ) : null}
                            {getProvenanceBadge(fact.provenance)}
                            {getReviewBadge(fact.review_status, hasConflict)}
                            {fact.is_time_sensitive ? (
                              <Badge variant="warning">
                                Time-sensitive
                                {fact.source_date_label
                                  ? ` (${fact.source_date_label})`
                                  : ""}
                              </Badge>
                            ) : null}
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {fact.source_page_number
                              ? `Page ${fact.source_page_number} · `
                              : ""}
                            Confidence {Math.round(fact.confidence * 100)}%
                          </span>
                        </div>

                        {isEditing ? (
                          <div className="space-y-2">
                            <textarea
                              rows={3}
                              value={editingContent}
                              onChange={(e) =>
                                setEditingContent(e.target.value)
                              }
                              disabled={isBusy}
                              aria-label="Edit fact content"
                              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                            <div className="flex items-center gap-2">
                              <Button
                                type="button"
                                size="sm"
                                disabled={
                                  isBusy || editingContent.trim().length === 0
                                }
                                onClick={() =>
                                  void handleFactAction(fact, {
                                    content: editingContent.trim(),
                                    review_status: "verified",
                                  })
                                }
                              >
                                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                                <span>Save &amp; Verify</span>
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={isBusy}
                                onClick={() => setEditingFactId(null)}
                              >
                                <X className="h-3.5 w-3.5" aria-hidden="true" />
                                <span>Cancel</span>
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <p className="text-sm">{fact.content}</p>
                        )}

                        {fact.supporting_excerpt ? (
                          <blockquote className="border-l-2 pl-3 text-xs italic text-muted-foreground">
                            Source excerpt: &ldquo;{fact.supporting_excerpt}&rdquo;
                          </blockquote>
                        ) : null}

                        {!isEditing ? (
                          <div className="flex flex-wrap items-center gap-2 pt-1">
                            {fact.review_status !== "verified" ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={isBusy}
                                onClick={() =>
                                  void handleFactAction(fact, {
                                    review_status: "verified",
                                  })
                                }
                              >
                                <CheckCircle2
                                  className="h-3.5 w-3.5 text-emerald-600"
                                  aria-hidden="true"
                                />
                                <span>Mark Verified</span>
                              </Button>
                            ) : null}
                            {fact.review_status !== "needs_review" ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={isBusy}
                                onClick={() =>
                                  void handleFactAction(fact, {
                                    review_status: "needs_review",
                                  })
                                }
                              >
                                <span>Flag Review</span>
                              </Button>
                            ) : null}
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              disabled={isBusy}
                              onClick={() => {
                                setEditingFactId(fact.id);
                                setEditingContent(fact.content);
                              }}
                            >
                              <Edit3 className="h-3.5 w-3.5" aria-hidden="true" />
                              <span>Edit</span>
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
