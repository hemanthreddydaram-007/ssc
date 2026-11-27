"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Bookmark,
  Flag,
  LayoutGrid,
  SkipForward,
} from "lucide-react";

import {
  ConnectionIndicator,
  type SaveConnectionState,
} from "@/components/test-player/ConnectionIndicator";
import { CountdownTimer } from "@/components/test-player/CountdownTimer";
import { QuestionPalette } from "@/components/test-player/QuestionPalette";
import { QuestionView } from "@/components/test-player/QuestionView";
import { SelfReportTagModal } from "@/components/test-player/SelfReportTagModal";
import { SubmitConfirmDialog } from "@/components/test-player/SubmitConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  getAttemptCurrent,
  getOptionKey,
  navigateAttempt,
  saveAttemptResponse,
  saveSelfReport,
  submitAttempt,
  type AttemptCurrentOut,
} from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { formatTimerModeLabel } from "@/lib/api/tests";
import { useKeyboardNav } from "@/lib/hooks/useKeyboardNav";
import { useServerTimer } from "@/lib/hooks/useServerTimer";

interface TestPlayerShellProps {
  attemptId: string;
}

function getDraftStorageKey(attemptId: string, testQuestionId: string): string {
  return `examcoach_draft:${attemptId}:${testQuestionId}`;
}

export function TestPlayerShell({ attemptId }: TestPlayerShellProps) {
  const router = useRouter();

  const [state, setState] = React.useState<AttemptCurrentOut | null>(null);
  const [selectedOptionKey, setSelectedOptionKey] = React.useState<
    string | null
  >(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [fatalError, setFatalError] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);

  const [connectionState, setConnectionState] =
    React.useState<SaveConnectionState>("saved");
  const [isBusy, setIsBusy] = React.useState(false);
  const [submitOpen, setSubmitOpen] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [mobilePaletteOpen, setMobilePaletteOpen] = React.useState(false);
  const [isSavingSelfReport, setIsSavingSelfReport] = React.useState(false);
  const [selfReportReason, setSelfReportReason] = React.useState<string | null>(
    null,
  );

  const syncCurrent = React.useCallback(
    async (signal?: AbortSignal) => {
      try {
        const current = await getAttemptCurrent(attemptId, signal);
        if (current.status !== "in_progress") {
          router.replace(`/attempts/${encodeURIComponent(attemptId)}/results`);
          return;
        }
        setState(current);
        setConnectionState("saved");
        setActionError(null);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setFatalError(
          error instanceof Error
            ? error.message
            : "Unable to load active test attempt.",
        );
      } finally {
        setIsLoading(false);
      }
    },
    [attemptId, router],
  );

  React.useEffect(() => {
    const controller = new AbortController();
    void syncCurrent(controller.signal);
    return () => controller.abort();
  }, [syncCurrent]);

  const currentQuestion = state?.current_question ?? null;

  // Restore committed answer or ephemeral sessionStorage draft on question change / refresh
  React.useEffect(() => {
    if (!currentQuestion) {
      setSelectedOptionKey(null);
      return;
    }
    setSelfReportReason(null);
    if (currentQuestion.selected_option_key) {
      setSelectedOptionKey(currentQuestion.selected_option_key);
      return;
    }
    try {
      const draft = window.sessionStorage.getItem(
        getDraftStorageKey(attemptId, currentQuestion.test_question_id),
      );
      setSelectedOptionKey(draft || null);
    } catch {
      setSelectedOptionKey(null);
    }
  }, [
    attemptId,
    currentQuestion?.test_question_id,
    currentQuestion?.selected_option_key,
    currentQuestion,
  ]);

  const activeExpiresAt = React.useMemo(() => {
    if (!state || state.status !== "in_progress") return null;
    if (state.timer_mode === "speed_challenge") {
      return state.current_question?.question_expires_at ?? null;
    }
    if (state.timer_mode === "exam_simulation") {
      return state.attempt_expires_at ?? null;
    }
    return null;
  }, [state]);

  const handleTimerExpire = React.useCallback(() => {
    // Ask server to transition expired question or attempt authoritatively
    void syncCurrent();
  }, [syncCurrent]);

  const { remainingMs } = useServerTimer({
    serverNowIso: state?.server_now ?? null,
    expiresAtIso: activeExpiresAt,
    enabled: Boolean(state && state.status === "in_progress"),
    onExpire: handleTimerExpire,
    onFocusResync: () => {
      void syncCurrent();
    },
  });

  const handleSelectOption = (optionKey: string) => {
    if (!currentQuestion || currentQuestion.locked_feedback) return;
    setSelectedOptionKey(optionKey);
    setActionError(null);
    try {
      window.sessionStorage.setItem(
        getDraftStorageKey(attemptId, currentQuestion.test_question_id),
        optionKey,
      );
    } catch {
      // sessionStorage unavailable
    }
  };

  const commitResponse = async (
    action: "answer" | "skip" | "mark_review" | "unmark_review",
    advance: boolean,
  ) => {
    if (!state || !currentQuestion) return;
    if (action === "answer" && !selectedOptionKey) {
      setActionError("Select an option before saving, or choose Skip.");
      return;
    }

    setIsBusy(true);
    setConnectionState("saving");
    setActionError(null);

    try {
      const res = await saveAttemptResponse(attemptId, {
        test_question_id: currentQuestion.test_question_id,
        selected_option_key:
          action === "answer" ? selectedOptionKey : currentQuestion.selected_option_key ?? undefined,
        action,
        advance,
      });

      try {
        window.sessionStorage.removeItem(
          getDraftStorageKey(attemptId, currentQuestion.test_question_id),
        );
      } catch {
        // ignore
      }

      setConnectionState("saved");
      if (res.next_state) {
        if (res.next_state.status !== "in_progress") {
          router.replace(`/attempts/${encodeURIComponent(attemptId)}/results`);
          return;
        }
        setState(res.next_state);
      } else if (res.locked_feedback) {
        setState((prev) => {
          if (!prev || !prev.current_question) return prev;
          return {
            ...prev,
            server_now: res.server_now,
            current_question: {
              ...prev.current_question,
              selected_option_key: res.selected_option_key ?? selectedOptionKey,
              status: res.status,
              is_marked_for_review: res.is_marked_for_review,
              locked_feedback: res.locked_feedback,
            },
          };
        });
      } else {
        await syncCurrent();
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setActionError(error.message);
        await syncCurrent();
      } else {
        setConnectionState("error");
        setActionError(
          error instanceof Error ? error.message : "Failed to save response.",
        );
      }
    } finally {
      setIsBusy(false);
    }
  };

  const handleNavigate = async (targetIndex: number) => {
    if (!state || state.timer_mode === "speed_challenge") return;
    setIsBusy(true);
    setActionError(null);
    try {
      const next = await navigateAttempt(attemptId, targetIndex);
      if (next.status !== "in_progress") {
        router.replace(`/attempts/${encodeURIComponent(attemptId)}/results`);
        return;
      }
      setState(next);
      setMobilePaletteOpen(false);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Unable to navigate.",
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleConfirmSubmit = async () => {
    setIsSubmitting(true);
    setActionError(null);
    try {
      await submitAttempt(attemptId);
      router.replace(`/attempts/${encodeURIComponent(attemptId)}/results`);
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Failed to submit attempt.",
      );
      setIsSubmitting(false);
    }
  };

  const allowNavigation =
    state !== null && state.timer_mode !== "speed_challenge";
  const isLastQuestion =
    state !== null && state.current_question_index >= state.total_questions - 1;
  const optionKeys = currentQuestion
    ? currentQuestion.options.map((o) => getOptionKey(o).toUpperCase())
    : [];
  const activeLockedFeedback =
    state?.locked_feedback ?? currentQuestion?.locked_feedback ?? null;

  useKeyboardNav({
    enabled: Boolean(
      state &&
        currentQuestion &&
        !submitOpen &&
        !mobilePaletteOpen &&
        !isBusy,
    ),
    optionKeys,
    onSelectOption: handleSelectOption,
    onNext: () => {
      if (currentQuestion?.locked_feedback && allowNavigation && !isLastQuestion) {
        void handleNavigate(state!.current_question_index + 1);
      } else if (selectedOptionKey) {
        void commitResponse("answer", true);
      } else {
        void commitResponse("skip", true);
      }
    },
    onPrevious:
      allowNavigation && state && state.current_question_index > 0
        ? () => void handleNavigate(state.current_question_index - 1)
        : undefined,
    onToggleReview: allowNavigation
      ? () =>
          void commitResponse(
            currentQuestion?.is_marked_for_review
              ? "unmark_review"
              : "mark_review",
            false,
          )
      : undefined,
    onSkip: () => void commitResponse("skip", true),
  });

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-16 text-center text-sm text-muted-foreground">
          Loading timed test session…
        </CardContent>
      </Card>
    );
  }

  if (fatalError || !state) {
    return (
      <div className="space-y-4">
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{fatalError ?? "Attempt not found."}</span>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/tests">Back to Tests</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4 pb-24 sm:pb-6">
      {/* Compact Sticky Top Bar */}
      <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-card/95 px-4 py-3 shadow-sm backdrop-blur">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">
            {state.test_title ?? "Practice Test"}
          </span>
          <Badge variant="secondary">
            {formatTimerModeLabel(state.timer_mode)}
          </Badge>
          <span className="text-xs font-medium text-muted-foreground">
            Question {state.current_question_index + 1} of{" "}
            {state.total_questions}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <ConnectionIndicator
            state={connectionState}
            errorMessage={actionError}
          />
          <CountdownTimer remainingMs={remainingMs} />
          {allowNavigation ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-[44px] sm:min-h-0 lg:hidden"
              onClick={() => setMobilePaletteOpen(true)}
            >
              <LayoutGrid className="h-4 w-4" aria-hidden="true" />
              <span>Palette</span>
            </Button>
          ) : null}
          <Button
            type="button"
            variant="destructive"
            size="sm"
            className="min-h-[44px] sm:min-h-0"
            onClick={() => setSubmitOpen(true)}
          >
            <Flag className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Submit</span>
          </Button>
        </div>
      </header>

      {actionError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{actionError}</span>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <div className="space-y-4 lg:col-span-3">
          {currentQuestion ? (
            <Card>
              <CardContent className="p-5 sm:p-6 space-y-5">
                <QuestionView
                  question={currentQuestion}
                  selectedOptionKey={selectedOptionKey}
                  lockedFeedback={activeLockedFeedback}
                  disabled={isBusy}
                  onSelectOption={handleSelectOption}
                />

                {activeLockedFeedback && currentQuestion.response_id ? (
                  <SelfReportTagModal
                    currentReason={selfReportReason}
                    isSaving={isSavingSelfReport}
                    onSave={async (reason) => {
                      const responseId = currentQuestion.response_id;
                      if (!responseId) return;
                      setIsSavingSelfReport(true);
                      try {
                        await saveSelfReport(attemptId, responseId, {
                          mistake_reason_self_report: reason,
                        });
                        setSelfReportReason(reason);
                      } finally {
                        setIsSavingSelfReport(false);
                      }
                    }}
                  />
                ) : null}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                All questions completed. Ready to submit!
              </CardContent>
            </Card>
          )}

          {/* Action Bar (sticky on mobile for ergonomic thumb reach) */}
          <div className="fixed inset-x-0 bottom-0 z-20 flex flex-wrap items-center justify-between gap-2 border-t bg-card/95 p-3 shadow-lg backdrop-blur sm:static sm:rounded-lg sm:border sm:shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              {allowNavigation ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-[44px] sm:min-h-0"
                  disabled={isBusy || state.current_question_index <= 0}
                  onClick={() =>
                    void handleNavigate(state.current_question_index - 1)
                  }
                >
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  <span>Previous</span>
                </Button>
              ) : null}
              {allowNavigation && currentQuestion ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-[44px] sm:min-h-0"
                  disabled={isBusy}
                  onClick={() =>
                    void commitResponse(
                      currentQuestion.is_marked_for_review
                        ? "unmark_review"
                        : "mark_review",
                      false,
                    )
                  }
                >
                  <Bookmark className="h-4 w-4" aria-hidden="true" />
                  <span className="hidden sm:inline">
                    {currentQuestion.is_marked_for_review
                      ? "Unmark Review"
                      : "Mark Review"}
                  </span>
                </Button>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {currentQuestion && !currentQuestion.locked_feedback ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="min-h-[44px] sm:min-h-0"
                    disabled={isBusy}
                    onClick={() => void commitResponse("skip", true)}
                  >
                    <SkipForward className="h-4 w-4" aria-hidden="true" />
                    <span>Skip</span>
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className="min-h-[44px] sm:min-h-0"
                    disabled={isBusy || !selectedOptionKey}
                    onClick={() =>
                      void commitResponse(
                        "answer",
                        state.timer_mode !== "learning_mode",
                      )
                    }
                  >
                    <span>
                      {state.timer_mode === "learning_mode"
                        ? "Check Answer"
                        : isLastQuestion
                          ? "Save Answer"
                          : "Save & Next"}
                    </span>
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </>
              ) : allowNavigation && !isLastQuestion ? (
                <Button
                  type="button"
                  size="sm"
                  disabled={isBusy}
                  onClick={() =>
                    void handleNavigate(state.current_question_index + 1)
                  }
                >
                  <span>Next Question</span>
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => setSubmitOpen(true)}
                >
                  Finish &amp; Submit
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Desktop Question Palette */}
        <aside className="hidden lg:block">
          <Card className="sticky top-20">
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Question Palette
                </h2>
                {!allowNavigation ? (
                  <span className="text-[11px] text-muted-foreground">
                    Sequential
                  </span>
                ) : null}
              </div>
              <QuestionPalette
                palette={state.palette}
                currentIndex={state.current_question_index}
                allowNavigation={allowNavigation && !isBusy}
                onSelectIndex={(idx) => void handleNavigate(idx)}
              />
            </CardContent>
          </Card>
        </aside>
      </div>

      {/* Mobile Palette Sheet */}
      {mobilePaletteOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Question palette"
          className="fixed inset-0 z-50 flex items-end bg-foreground/40 backdrop-blur-sm lg:hidden"
        >
          <div
            className="fixed inset-0"
            aria-hidden="true"
            onClick={() => setMobilePaletteOpen(false)}
          />
          <div className="relative z-10 w-full rounded-t-xl border-t bg-card p-5 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Jump to Question</h2>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setMobilePaletteOpen(false)}
              >
                Close
              </Button>
            </div>
            <QuestionPalette
              palette={state.palette}
              currentIndex={state.current_question_index}
              allowNavigation={allowNavigation && !isBusy}
              onSelectIndex={(idx) => void handleNavigate(idx)}
            />
          </div>
        </div>
      ) : null}

      <SubmitConfirmDialog
        open={submitOpen}
        palette={state.palette}
        isSubmitting={isSubmitting}
        onClose={() => setSubmitOpen(false)}
        onConfirm={() => void handleConfirmSubmit()}
      />
    </div>
  );
}
