"use client";

import * as React from "react";

import {
  computeClockOffsetMs,
  computeRemainingMs,
} from "@/lib/utils/timer";

interface UseServerTimerOptions {
  serverNowIso: string | null;
  expiresAtIso: string | null;
  enabled: boolean;
  onExpire: () => void;
  onFocusResync?: () => void;
}

/**
 * Computes countdown strictly from server `expires_at` and clock offset
 * (`Date.now() - Date.parse(server_now)`), resilient to browser tab throttling.
 */
export function useServerTimer({
  serverNowIso,
  expiresAtIso,
  enabled,
  onExpire,
  onFocusResync,
}: UseServerTimerOptions) {
  const clockOffsetRef = React.useRef<number>(0);
  const expiredKeyRef = React.useRef<string | null>(null);
  const onExpireRef = React.useRef(onExpire);
  const onFocusResyncRef = React.useRef(onFocusResync);

  React.useEffect(() => {
    onExpireRef.current = onExpire;
  }, [onExpire]);

  React.useEffect(() => {
    onFocusResyncRef.current = onFocusResync;
  }, [onFocusResync]);

  React.useEffect(() => {
    if (!serverNowIso) return;
    clockOffsetRef.current = computeClockOffsetMs(serverNowIso);
  }, [serverNowIso]);

  const computeCurrentRemaining = React.useCallback((): number | null => {
    return computeRemainingMs(expiresAtIso, clockOffsetRef.current);
  }, [expiresAtIso]);

  const [remainingMs, setRemainingMs] = React.useState<number | null>(() =>
    computeCurrentRemaining(),
  );

  React.useEffect(() => {
    if (!enabled || !expiresAtIso) {
      setRemainingMs(null);
      return;
    }

    const updateTick = () => {
      const next = computeCurrentRemaining();
      setRemainingMs(next);
      if (next !== null && next <= 0 && expiredKeyRef.current !== expiresAtIso) {
        expiredKeyRef.current = expiresAtIso;
        onExpireRef.current();
      }
    };

    updateTick();
    const intervalId = window.setInterval(updateTick, 250);

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        updateTick();
        onFocusResyncRef.current?.();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [enabled, expiresAtIso, computeCurrentRemaining]);

  return { remainingMs };
}
