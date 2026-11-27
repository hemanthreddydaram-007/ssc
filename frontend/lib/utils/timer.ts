/**
 * Pure server-synchronized countdown helpers.
 * `clockOffsetMs = clientNowMs - serverNowMs`.
 */
export function computeClockOffsetMs(
  serverNowIso: string,
  clientNowMs: number = Date.now(),
): number {
  const parsed = Date.parse(serverNowIso);
  if (Number.isNaN(parsed)) {
    return 0;
  }
  return clientNowMs - parsed;
}

export function computeRemainingMs(
  expiresAtIso: string | null | undefined,
  clockOffsetMs: number,
  clientNowMs: number = Date.now(),
): number | null {
  if (!expiresAtIso) {
    return null;
  }
  const targetMs = Date.parse(expiresAtIso);
  if (Number.isNaN(targetMs)) {
    return null;
  }
  const estimatedServerNow = clientNowMs - clockOffsetMs;
  return Math.max(0, targetMs - estimatedServerNow);
}

export function formatCountdownClock(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}
