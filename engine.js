/**
 * Pure domain logic for SSC CHSL Time Trainer.
 * Handles scoring (+2 / -0.50), 36s 4-quadrant autopsy, final-minute panic detection,
 * blind time calibration, adaptive overspeed pacing, and weak-question filtering.
 */

export const EXAM_DURATION_SEC = 15 * 60;
export const STABILIZE_DURATION_SEC = 17 * 60;
export const OVERSPEED_DURATION_SEC = 13 * 60 + 30;
export const FAST_THRESHOLD_MS = 36_000;
export const PANIC_WINDOW_MS = 60_000;
export const GATE_LOCK_MS = 7_000;
export const MARKS_RIGHT = 2.0;
export const MARKS_WRONG = 0.5;

export const CALIBRATION_OPTIONS = [
  {
    id: "under30",
    label: "Under 30s",
    matches: (ms) => ms < 30_000
  },
  {
    id: "30to60",
    label: "30s–60s",
    matches: (ms) => ms >= 30_000 && ms <= 60_000
  },
  {
    id: "over60",
    label: "Over 60s",
    matches: (ms) => ms > 60_000
  }
];

/**
 * Formats countdown clock milliseconds as MM:SS without premature 00:00 flicker.
 */
export function formatClock(remainingMs) {
  const clampedMs = Math.max(0, remainingMs);
  const totalSeconds = Math.ceil(clampedMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Formats spent duration clearly: seconds with 1 decimal under 60s (so >36s is unambiguous),
 * and "Xm Ys" for 60s and above.
 */
export function formatDuration(ms) {
  const safeMs = Math.max(0, ms);
  if (safeMs < 60_000) {
    return `${(safeMs / 1000).toFixed(1)}s`;
  }
  const roundedSec = Math.round(safeMs / 1000);
  const minutes = Math.floor(roundedSec / 60);
  const seconds = roundedSec % 60;
  return `${minutes}m ${seconds}s`;
}

/**
 * Computes adaptive sectional timer (v2) from the last 2 full exam runs of a section.
 */
export function computeAdaptiveTimer(runs, section) {
  const eligible = (runs || []).filter(
    (run) => !run.isRetry && run.section === section && run.mode === "exam"
  );

  if (eligible.length < 2) {
    return {
      durationSec: EXAM_DURATION_SEC,
      label: "15:00",
      avgAccuracy: null,
      reason: `Real exam pace (complete ${2 - eligible.length} more full ${section} exam run${eligible.length === 1 ? "" : "s"} to adapt)`
    };
  }

  const lastTwo = eligible.slice(-2);
  const avgAccuracy = (lastTwo[0].accuracyPct + lastTwo[1].accuracyPct) / 2;
  const bothAtStandardOrFaster = lastTwo.every((r) => r.durationSec <= EXAM_DURATION_SEC);

  if (avgAccuracy < 60) {
    return {
      durationSec: STABILIZE_DURATION_SEC,
      label: "17:00",
      avgAccuracy,
      reason: `Last 2 runs avg ${avgAccuracy.toFixed(1)}% accuracy (<60%) — 17:00 to stabilize accuracy`
    };
  }

  if (avgAccuracy > 80 && bothAtStandardOrFaster) {
    return {
      durationSec: OVERSPEED_DURATION_SEC,
      label: "13:30",
      avgAccuracy,
      reason: `Last 2 runs avg ${avgAccuracy.toFixed(1)}% (>80% at ≤15:00) — 13:30 overspeed conditioning`
    };
  }

  return {
    durationSec: EXAM_DURATION_SEC,
    label: "15:00",
    avgAccuracy,
    reason:
      avgAccuracy > 80
        ? `Last 2 runs avg ${avgAccuracy.toFixed(1)}% — stabilizing at 15:00 before overspeed`
        : `Last 2 runs avg ${avgAccuracy.toFixed(1)}% (60–80%) — real 15:00 exam pace`
  };
}

/**
 * Analyzes a completed run into headline metrics, 4-quadrant classification,
 * panic detections, slowest question, and retry targets.
 */
export function analyzeRun({ questions, answers, telemetry, durationSec, totalElapsedMs }) {
  const items = questions.map((question, index) => {
    const selectedIndex = answers[index] ?? null;
    const stats = telemetry[index] || { totalMs: 0, visits: 0, savedRemainingMs: null };
    const totalMs = Math.max(0, stats.totalMs || 0);
    const visits = stats.visits || 0;
    const savedRemainingMs = stats.savedRemainingMs ?? null;

    const isAttempted = selectedIndex !== null;
    const isCorrect = isAttempted && selectedIndex === question.correctIndex;
    const isWrong = isAttempted && selectedIndex !== question.correctIndex;
    const isSlow = totalMs > FAST_THRESHOLD_MS;
    const isPanicError = isWrong && savedRemainingMs !== null && savedRemainingMs <= PANIC_WINDOW_MS;

    let quadrant = "unattempted";
    if (isAttempted) {
      if (isCorrect && !isSlow) quadrant = "fastRight";
      else if (isCorrect && isSlow) quadrant = "slowRight";
      else if (isWrong && !isSlow) quadrant = "fastWrong";
      else quadrant = "slowWrong";
    }

    return {
      index,
      number: index + 1,
      question,
      selectedIndex,
      isAttempted,
      isCorrect,
      isWrong,
      isSlow,
      isPanicError,
      totalMs,
      visits,
      savedRemainingMs,
      quadrant
    };
  });

  const quadrants = {
    fastRight: items.filter((item) => item.quadrant === "fastRight"),
    slowRight: items.filter((item) => item.quadrant === "slowRight"),
    fastWrong: items.filter((item) => item.quadrant === "fastWrong"),
    slowWrong: items.filter((item) => item.quadrant === "slowWrong"),
    unattempted: items.filter((item) => item.quadrant === "unattempted")
  };

  const correctCount = quadrants.fastRight.length + quadrants.slowRight.length;
  const wrongCount = quadrants.fastWrong.length + quadrants.slowWrong.length;
  const attemptedCount = correctCount + wrongCount;
  const unattemptedCount = quadrants.unattempted.length;

  const netScore = Number((correctCount * MARKS_RIGHT - wrongCount * MARKS_WRONG).toFixed(2));
  const maxScore = questions.length * MARKS_RIGHT;
  const accuracyPct = attemptedCount > 0 ? Number(((correctCount / attemptedCount) * 100).toFixed(1)) : 0;

  const panicErrors = items.filter((item) => item.isPanicError);
  const slowWrongTotalMs = quadrants.slowWrong.reduce((sum, item) => sum + item.totalMs, 0);
  const slowWrongTotalSec = slowWrongTotalMs / 1000;
  const opportunityCostAttempts = Number((slowWrongTotalSec / 36).toFixed(1));

  // Slowest question for Blind Time Calibration (prefer visited questions on tie)
  const slowestItem = items.reduce((slowest, item) => {
    if (!slowest) return item;
    if (item.totalMs > slowest.totalMs) return item;
    if (item.totalMs === slowest.totalMs && item.visits > slowest.visits) return item;
    return slowest;
  }, null);

  // Weak PYQs for One-Click Retry Loop: any wrong answer OR any slow (>36s) question
  const weakItems = items.filter((item) => item.isWrong || item.isSlow);
  const weakQuestions = weakItems.map((item) => item.question);

  return {
    durationSec,
    totalElapsedMs,
    totalQuestions: questions.length,
    attemptedCount,
    correctCount,
    wrongCount,
    unattemptedCount,
    netScore,
    maxScore,
    accuracyPct,
    panicErrors,
    slowWrongTotalMs,
    slowWrongTotalSec,
    opportunityCostAttempts,
    slowestItem,
    weakItems,
    weakQuestions,
    quadrants,
    items
  };
}

/**
 * Evaluates the user's blind time calibration guess against reality.
 */
export function evaluateCalibration(slowestItem, guessId) {
  const band = CALIBRATION_OPTIONS.find((opt) => opt.id === guessId) || CALIBRATION_OPTIONS[0];
  const actualMs = slowestItem ? slowestItem.totalMs : 0;
  const visits = slowestItem ? slowestItem.visits : 0;
  const actualFormatted = formatDuration(actualMs);
  const matched = band.matches(actualMs);
  const visitWord = visits === 1 ? "visit" : "visits";

  return {
    guessId: band.id,
    guessLabel: band.label,
    actualMs,
    actualFormatted,
    visits,
    matched,
    summaryText: `You guessed ${band.label}. Reality: ${actualFormatted} across ${visits} ${visitWord}.`
  };
}
