"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Play, Timer } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { DocumentItem } from "@/lib/api/documents";
import {
  formatExamName,
  formatSubjectLabel,
  type ExamConfig,
} from "@/lib/api/examConfigs";
import type { SubjectOut, TopicSummaryOut } from "@/lib/api/knowledge";
import { startTestAttempt } from "@/lib/api/attempts";
import {
  createTest,
  previewTest,
  type OriginMode,
  type ShowExplanationAfter,
  type TestPreviewResponse,
  type TimerMode,
} from "@/lib/api/tests";
import { cn } from "@/lib/utils/cn";
import { loadPreferences } from "@/lib/utils/preferences";

interface TestBuilderFormProps {
  examConfigs: readonly ExamConfig[];
  documents: readonly DocumentItem[];
  subjects: readonly SubjectOut[];
  topics: readonly TopicSummaryOut[];
  initialQuestionIds?: string[];
  initialDocumentId?: string;
  initialSubjectCode?: string;
  initialTopicId?: string;
}

const SPEED_PRESETS = [15, 25, 35, 45, 60] as const;

export function TestBuilderForm({
  examConfigs,
  documents,
  subjects,
  topics,
  initialQuestionIds = [],
  initialDocumentId = "",
  initialSubjectCode = "",
  initialTopicId = "",
}: TestBuilderFormProps) {
  const router = useRouter();

  const initialPrefs = React.useMemo(() => loadPreferences(), []);

  const [title, setTitle] = React.useState("Practice Test");
  const [examConfigId, setExamConfigId] = React.useState(
    (examConfigs.find((c) => c.exam_code === initialPrefs.default_exam_code) ??
      examConfigs.find((c) => c.exam_code === "ssc_chsl_tier_1"))?.id ?? "",
  );
  const [selectedDocIds, setSelectedDocIds] = React.useState<string[]>(
    initialDocumentId ? [initialDocumentId] : [],
  );
  const [selectedSubjectCodes, setSelectedSubjectCodes] = React.useState<
    string[]
  >(initialSubjectCode ? [initialSubjectCode] : []);
  const [selectedTopicIds, setSelectedTopicIds] = React.useState<string[]>(
    initialTopicId ? [initialTopicId] : [],
  );
  const [fixedQuestionIds, setFixedQuestionIds] =
    React.useState<string[]>(initialQuestionIds);

  const [questionCount, setQuestionCount] = React.useState(
    initialQuestionIds.length > 0 ? initialQuestionIds.length : 10,
  );
  const [originMode, setOriginMode] = React.useState<OriginMode>("mixed");
  const [timerMode, setTimerMode] =
    React.useState<TimerMode>("speed_challenge");
  const [perQuestionSeconds, setPerQuestionSeconds] = React.useState(
    initialPrefs.default_speed_challenge_seconds,
  );
  const [totalDurationMinutes, setTotalDurationMinutes] = React.useState(15);
  const [autoAdvanceOnTimeout, setAutoAdvanceOnTimeout] = React.useState(true);
  const [pointsPerQuestion, setPointsPerQuestion] = React.useState(2);
  const [negativeMarkingEnabled, setNegativeMarkingEnabled] =
    React.useState(true);
  const [negativePoints, setNegativePoints] = React.useState(0.5);
  const [shuffleQuestions, setShuffleQuestions] = React.useState(false);
  const [shuffleOptions, setShuffleOptions] = React.useState(false);
  const [showExplanationAfter, setShowExplanationAfter] =
    React.useState<ShowExplanationAfter>("after_submission");
  const [includeNeedsReview, setIncludeNeedsReview] = React.useState(
    initialQuestionIds.length > 0,
  );

  const [preview, setPreview] = React.useState<TestPreviewResponse | null>(
    null,
  );
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);

  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (examConfigId === "" && examConfigs.length > 0) {
      const def = examConfigs.find((c) => c.exam_code === "ssc_chsl_tier_1");
      if (def) setExamConfigId(def.id);
    }
  }, [examConfigs, examConfigId]);

  React.useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setPreviewLoading(true);
      setPreviewError(null);
      previewTest(
        {
          document_ids: selectedDocIds.length > 0 ? selectedDocIds : undefined,
          subject_codes:
            selectedSubjectCodes.length > 0 ? selectedSubjectCodes : undefined,
          topic_ids:
            selectedTopicIds.length > 0 ? selectedTopicIds : undefined,
          question_ids:
            fixedQuestionIds.length > 0 ? fixedQuestionIds : undefined,
          origin_mode: originMode,
          question_count: questionCount,
          include_needs_review: includeNeedsReview,
        },
        controller.signal,
      )
        .then((res) => setPreview(res))
        .catch((error) => {
          if (error instanceof DOMException && error.name === "AbortError") {
            return;
          }
          setPreviewError(
            error instanceof Error
              ? error.message
              : "Failed to preview matching question pool.",
          );
        })
        .finally(() => setPreviewLoading(false));
    }, 200);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [
    selectedDocIds,
    selectedSubjectCodes,
    selectedTopicIds,
    fixedQuestionIds,
    originMode,
    questionCount,
    includeNeedsReview,
  ]);

  const toggleItem = (
    list: string[],
    setter: React.Dispatch<React.SetStateAction<string[]>>,
    id: string,
  ) => {
    setter(
      list.includes(id) ? list.filter((x) => x !== id) : [...list, id],
    );
  };

  const handleCreateAndStart = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitError(null);
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setSubmitError("Test title is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const created = await createTest({
        title: trimmedTitle,
        exam_config_id: examConfigId || null,
        document_ids: selectedDocIds.length > 0 ? selectedDocIds : undefined,
        subject_codes:
          selectedSubjectCodes.length > 0 ? selectedSubjectCodes : undefined,
        topic_ids: selectedTopicIds.length > 0 ? selectedTopicIds : undefined,
        question_ids:
          fixedQuestionIds.length > 0 ? fixedQuestionIds : undefined,
        question_count: questionCount,
        origin_mode: originMode,
        timer_mode: timerMode,
        per_question_seconds:
          timerMode === "speed_challenge" ? perQuestionSeconds : 35,
        total_duration_seconds:
          timerMode === "exam_simulation"
            ? Math.max(60, totalDurationMinutes * 60)
            : undefined,
        auto_advance_on_timeout: autoAdvanceOnTimeout,
        points_per_question: pointsPerQuestion,
        negative_marking_enabled: negativeMarkingEnabled,
        negative_points: negativeMarkingEnabled ? negativePoints : 0,
        shuffle_questions: shuffleQuestions,
        shuffle_options: shuffleOptions,
        show_explanation_after:
          timerMode === "learning_mode"
            ? showExplanationAfter
            : "after_submission",
        include_needs_review: includeNeedsReview,
      });

      const started = await startTestAttempt(created.id);
      router.push(`/attempts/${encodeURIComponent(started.attempt_id)}`);
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Failed to create test.",
      );
      setIsSubmitting(false);
    }
  };

  const filteredTopics =
    selectedSubjectCodes.length > 0
      ? topics.filter((t) => selectedSubjectCodes.includes(t.subject_code))
      : topics;

  return (
    <form onSubmit={handleCreateAndStart} className="min-w-0 max-w-full space-y-6">
      {fixedQuestionIds.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
          <span>
            Building test from{" "}
            <strong>{fixedQuestionIds.length} selected questions</strong> from
            the Question Bank.
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setFixedQuestionIds([])}
          >
            Clear Question Selection
          </Button>
        </div>
      ) : null}

      <div className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          {/* General & Source */}
          <Card className="min-w-0 overflow-hidden">
            <CardHeader>
              <CardTitle>Test Configuration</CardTitle>
              <CardDescription>
                Choose source documents, subjects, topics, and question mix.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="min-w-0 sm:col-span-2">
                  <label
                    htmlFor="test-title"
                    className="block text-sm font-medium"
                  >
                    Test Title <span className="text-destructive">*</span>
                  </label>
                  <input
                    id="test-title"
                    type="text"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="mt-1.5 w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>

                <div className="min-w-0">
                  <label
                    htmlFor="test-exam"
                    className="block text-sm font-medium"
                  >
                    Exam Pack
                  </label>
                  <select
                    id="test-exam"
                    value={examConfigId}
                    onChange={(e) => setExamConfigId(e.target.value)}
                    className="mt-1.5 w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="">General</option>
                    {examConfigs.map((cfg) => (
                      <option key={cfg.id} value={cfg.id}>
                        {formatExamName(cfg.name)}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="min-w-0">
                  <label
                    htmlFor="test-count"
                    className="block text-sm font-medium"
                  >
                    Question Count
                  </label>
                  <input
                    id="test-count"
                    type="number"
                    min={1}
                    max={100}
                    value={questionCount}
                    onChange={(e) =>
                      setQuestionCount(
                        Math.max(1, Math.min(100, Number(e.target.value) || 1)),
                      )
                    }
                    className="mt-1.5 w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>

                <div className="min-w-0">
                  <label
                    htmlFor="test-origin"
                    className="block text-sm font-medium"
                  >
                    Question Source
                  </label>
                  <select
                    id="test-origin"
                    value={originMode}
                    onChange={(e) =>
                      setOriginMode(e.target.value as OriginMode)
                    }
                    className="mt-1.5 w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="mixed">Mixed (Extracted + Generated)</option>
                    <option value="extracted">Extracted from material only</option>
                    <option value="generated">AI generated only</option>
                  </select>
                </div>

                <div className="flex min-w-0 items-end">
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={includeNeedsReview}
                      onChange={(e) => setIncludeNeedsReview(e.target.checked)}
                      className="h-4 w-4 shrink-0 rounded border-input"
                    />
                    <span>Include questions flagged &ldquo;needs review&rdquo;</span>
                  </label>
                </div>
              </div>

              {fixedQuestionIds.length === 0 ? (
                <div className="min-w-0 space-y-4 border-t pt-4">
                  {documents.length > 0 ? (
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Source Documents (leave empty for all)
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {documents.map((doc) => {
                          const active = selectedDocIds.includes(doc.id);
                          return (
                            <button
                              key={doc.id}
                              type="button"
                              onClick={() =>
                                toggleItem(
                                  selectedDocIds,
                                  setSelectedDocIds,
                                  doc.id,
                                )
                              }
                              className={cn(
                                "max-w-full whitespace-normal break-words rounded-md border px-2.5 py-1 text-left text-xs font-medium transition-colors",
                                active
                                  ? "border-primary bg-primary text-primary-foreground"
                                  : "bg-muted/40 text-foreground hover:bg-accent",
                              )}
                            >
                              {doc.title}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}

                  {subjects.length > 0 ? (
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Subjects
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {subjects.map((sub) => {
                          const active = selectedSubjectCodes.includes(
                            sub.subject_code,
                          );
                          return (
                            <button
                              key={sub.subject_code}
                              type="button"
                              onClick={() =>
                                toggleItem(
                                  selectedSubjectCodes,
                                  setSelectedSubjectCodes,
                                  sub.subject_code,
                                )
                              }
                              className={cn(
                                "max-w-full whitespace-normal break-words rounded-md border px-2.5 py-1 text-left text-xs font-medium transition-colors",
                                active
                                  ? "border-primary bg-primary text-primary-foreground"
                                  : "bg-muted/40 text-foreground hover:bg-accent",
                              )}
                            >
                              {sub.display_name}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}

                  {filteredTopics.length > 0 ? (
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Topics
                      </p>
                      <div className="mt-2 flex max-h-32 flex-wrap gap-2 overflow-y-auto">
                        {filteredTopics.map((topic) => {
                          const active = selectedTopicIds.includes(topic.id);
                          return (
                            <button
                              key={topic.id}
                              type="button"
                              onClick={() =>
                                toggleItem(
                                  selectedTopicIds,
                                  setSelectedTopicIds,
                                  topic.id,
                                )
                              }
                              className={cn(
                                "max-w-full whitespace-normal break-words rounded-md border px-2.5 py-1 text-left text-xs font-medium transition-colors",
                                active
                                  ? "border-primary bg-primary text-primary-foreground"
                                  : "bg-muted/40 text-foreground hover:bg-accent",
                              )}
                            >
                              {topic.name}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>

          {/* Timer & Scoring Mode */}
          <Card className="min-w-0 overflow-hidden">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Timer className="h-4 w-4 text-primary" aria-hidden="true" />
                <CardTitle>Timer Mode &amp; Marking</CardTitle>
              </div>
              <CardDescription>
                Choose how timing and answer feedback behave during the test.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3">
                {(
                  [
                    {
                      id: "speed_challenge",
                      title: "Speed Challenge",
                      desc: "Per-question countdown (35s default). Builds speed; moves forward sequentially.",
                    },
                    {
                      id: "exam_simulation",
                      title: "Exam Simulation",
                      desc: "One overall exam timer with free navigation & question palette like real SSC CBT.",
                    },
                    {
                      id: "learning_mode",
                      title: "Learning Mode",
                      desc: "Untimed study mode with instant or end-of-test explanations and self-reflection tags.",
                    },
                  ] as const
                ).map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => {
                      setTimerMode(mode.id);
                      if (mode.id === "learning_mode") {
                        setShowExplanationAfter("after_question");
                      }
                    }}
                    className={cn(
                      "min-w-0 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      timerMode === mode.id
                        ? "border-primary bg-primary/5 ring-1 ring-primary"
                        : "hover:bg-muted/40",
                    )}
                  >
                    <p className="text-sm font-semibold">{mode.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {mode.desc}
                    </p>
                  </button>
                ))}
              </div>

              {timerMode === "speed_challenge" ? (
                <div className="space-y-3 rounded-md border bg-muted/30 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium">
                      Seconds per question:
                    </span>
                    {SPEED_PRESETS.map((sec) => (
                      <Button
                        key={sec}
                        type="button"
                        size="sm"
                        variant={
                          perQuestionSeconds === sec ? "default" : "outline"
                        }
                        onClick={() => setPerQuestionSeconds(sec)}
                      >
                        {sec}s
                      </Button>
                    ))}
                    <input
                      type="number"
                      min={5}
                      max={300}
                      value={perQuestionSeconds}
                      onChange={(e) =>
                        setPerQuestionSeconds(
                          Math.max(5, Math.min(300, Number(e.target.value) || 35)),
                        )
                      }
                      aria-label="Custom seconds per question"
                      className="w-20 rounded-md border border-input bg-background px-2.5 py-1 text-sm"
                    />
                  </div>
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={autoAdvanceOnTimeout}
                      onChange={(e) => setAutoAdvanceOnTimeout(e.target.checked)}
                      className="h-4 w-4 shrink-0 rounded border-input"
                    />
                    <span>Automatically advance to next question on timeout</span>
                  </label>
                </div>
              ) : timerMode === "exam_simulation" ? (
                <div className="rounded-md border bg-muted/30 p-4">
                  <label
                    htmlFor="total-duration-min"
                    className="block text-sm font-medium"
                  >
                    Total Exam Duration (minutes)
                  </label>
                  <input
                    id="total-duration-min"
                    type="number"
                    min={1}
                    max={180}
                    value={totalDurationMinutes}
                    onChange={(e) =>
                      setTotalDurationMinutes(
                        Math.max(1, Math.min(180, Number(e.target.value) || 15)),
                      )
                    }
                    className="mt-1.5 w-32 rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                  />
                </div>
              ) : (
                <div className="rounded-md border bg-muted/30 p-4">
                  <label
                    htmlFor="learning-explain-when"
                    className="block text-sm font-medium"
                  >
                    Show Explanations
                  </label>
                  <select
                    id="learning-explain-when"
                    value={showExplanationAfter}
                    onChange={(e) =>
                      setShowExplanationAfter(
                        e.target.value as ShowExplanationAfter,
                      )
                    }
                    className="mt-1.5 w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm sm:max-w-xs"
                  >
                    <option value="after_question">
                      After each question (when checked)
                    </option>
                    <option value="after_submission">
                      After final test submission
                    </option>
                  </select>
                </div>
              )}

              <details className="border-t pt-3">
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
                  Scoring &amp; shuffle options (default: +2 / −0.5 negative marking)
                </summary>
                <div className="mt-4 space-y-4">
                  <div className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-3">
                    <div className="min-w-0">
                      <label
                        htmlFor="points-per-q"
                        className="block text-xs font-medium text-muted-foreground"
                      >
                        Marks per Correct Answer
                      </label>
                      <input
                        id="points-per-q"
                        type="number"
                        step="0.25"
                        min={0.25}
                        value={pointsPerQuestion}
                        onChange={(e) =>
                          setPointsPerQuestion(Number(e.target.value) || 1)
                        }
                        className="mt-1 w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                      />
                    </div>
                    <div className="flex min-w-0 items-center sm:pt-5">
                      <label className="flex cursor-pointer items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={negativeMarkingEnabled}
                          onChange={(e) =>
                            setNegativeMarkingEnabled(e.target.checked)
                          }
                          className="h-4 w-4 shrink-0 rounded border-input"
                        />
                        <span>Negative marking</span>
                      </label>
                    </div>
                    {negativeMarkingEnabled ? (
                      <div className="min-w-0">
                        <label
                          htmlFor="neg-points"
                          className="block text-xs font-medium text-muted-foreground"
                        >
                          Penalty per Incorrect
                        </label>
                        <input
                          id="neg-points"
                          type="number"
                          step="0.25"
                          min={0}
                          value={negativePoints}
                          onChange={(e) =>
                            setNegativePoints(Number(e.target.value) || 0)
                          }
                          className="mt-1 w-full min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                        />
                      </div>
                    ) : null}
                  </div>

                  <div className="flex flex-wrap gap-5 pt-1">
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={shuffleQuestions}
                        onChange={(e) => setShuffleQuestions(e.target.checked)}
                        className="h-4 w-4 shrink-0 rounded border-input"
                      />
                      <span>Shuffle questions</span>
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={shuffleOptions}
                        onChange={(e) => setShuffleOptions(e.target.checked)}
                        className="h-4 w-4 shrink-0 rounded border-input"
                      />
                      <span>Shuffle options</span>
                    </label>
                  </div>
                </div>
              </details>
            </CardContent>
          </Card>
        </div>

        {/* Live Pool Preview */}
        <div className="min-w-0 space-y-4">
          <Card className="min-w-0 overflow-hidden lg:sticky lg:top-6">
            <CardHeader>
              <CardTitle>Question Pool Preview</CardTitle>
              <CardDescription>
                Live matching question availability before starting.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {previewError ? (
                <p className="text-sm text-destructive" role="alert">
                  {previewError}
                </p>
              ) : previewLoading && !preview ? (
                <p className="text-sm text-muted-foreground">
                  Checking available questions…
                </p>
              ) : preview ? (
                <>
                  <div className="rounded-md border bg-muted/40 p-3">
                    <p className="text-xs text-muted-foreground">
                      Matching Questions Available
                    </p>
                    <p className="mt-1 text-2xl font-semibold">
                      {preview.available_count}
                    </p>
                  </div>

                  {preview.can_satisfy ? (
                    <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-2.5 text-xs text-emerald-900">
                      <CheckCircle2
                        className="h-4 w-4 shrink-0"
                        aria-hidden="true"
                      />
                      <span>
                        Enough questions available for {questionCount}-question
                        test.
                      </span>
                    </div>
                  ) : (
                    <div className="space-y-2.5 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                      <div className="flex items-start gap-2">
                        <AlertCircle
                          className="mt-0.5 h-4 w-4 shrink-0"
                          aria-hidden="true"
                        />
                        <div>
                          <p className="font-medium">
                            {preview.shortfall_reason ??
                              `Only ${preview.available_count} matching questions available (requested ${questionCount}).`}
                          </p>
                          {preview.available_count === 0 ? (
                            <p className="mt-1 text-amber-800">
                              {!includeNeedsReview
                                ? "Imported or newly extracted questions marked “needs review” are hidden unless enabled."
                                : "No questions match your current filters yet. Import PYQs or extract questions from a PDF."}
                            </p>
                          ) : (
                            <p className="mt-1 text-amber-800">
                              Lower Question Count to {preview.available_count}{" "}
                              or broaden your filters.
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {!includeNeedsReview ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 bg-background text-xs"
                            onClick={() => setIncludeNeedsReview(true)}
                          >
                            Include unreviewed questions
                          </Button>
                        ) : null}
                        {preview.available_count > 0 &&
                        preview.available_count < questionCount ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 bg-background text-xs"
                            onClick={() =>
                              setQuestionCount(preview.available_count)
                            }
                          >
                            Use all {preview.available_count} available
                          </Button>
                        ) : null}
                        {preview.available_count === 0 ? (
                          <>
                            <Button
                              asChild
                              variant="outline"
                              size="sm"
                              className="h-7 bg-background text-xs"
                            >
                              <Link href="/question-bank">
                                Import PYQs / Question Bank
                              </Link>
                            </Button>
                            <Button
                              asChild
                              variant="outline"
                              size="sm"
                              className="h-7 bg-background text-xs"
                            >
                              <Link href="/library">Upload PDF</Link>
                            </Button>
                          </>
                        ) : null}
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(preview.by_difficulty).map(([k, v]) => (
                      <Badge key={k} variant="outline" className="capitalize">
                        {k}: {v ?? 0}
                      </Badge>
                    ))}
                  </div>

                  {Object.keys(preview.by_subject).length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(preview.by_subject).map(([code, cnt]) => (
                        <Badge key={code} variant="secondary">
                          {formatSubjectLabel(code)}: {cnt}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : null}

              {submitError ? (
                <div
                  role="alert"
                  className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-800"
                >
                  <AlertCircle
                    className="mt-0.5 h-4 w-4 shrink-0"
                    aria-hidden="true"
                  />
                  <span>{submitError}</span>
                </div>
              ) : null}

              <Button
                type="submit"
                className="w-full"
                disabled={isSubmitting || preview?.can_satisfy === false}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                <span>
                  {isSubmitting ? "Creating & Starting…" : "Create & Start Test"}
                </span>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </form>
  );
}
