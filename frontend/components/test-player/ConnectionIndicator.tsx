import { Cloud, CloudOff, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils/cn";

export type SaveConnectionState = "saved" | "saving" | "error";

interface ConnectionIndicatorProps {
  state: SaveConnectionState;
  errorMessage?: string | null;
}

export function ConnectionIndicator({
  state,
  errorMessage,
}: ConnectionIndicatorProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      title={errorMessage ?? undefined}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        state === "saved" &&
          "border-emerald-200 bg-emerald-50 text-emerald-800",
        state === "saving" && "border-amber-200 bg-amber-50 text-amber-800",
        state === "error" && "border-red-200 bg-red-50 text-red-800",
      )}
    >
      {state === "saving" ? (
        <>
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
          <span>Saving…</span>
        </>
      ) : state === "error" ? (
        <>
          <CloudOff className="h-3 w-3" aria-hidden="true" />
          <span>Save issue — retrying</span>
        </>
      ) : (
        <>
          <Cloud className="h-3 w-3" aria-hidden="true" />
          <span>Saved</span>
        </>
      )}
    </div>
  );
}
