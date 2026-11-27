"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";

export const MISTAKE_REASON_OPTIONS = [
  { value: "", label: "Not tagged" },
  { value: "guessed", label: "I guessed" },
  {
    value: "knew_method_made_mistake",
    label: "I knew the method but made a mistake",
  },
  {
    value: "did_not_understand_concept",
    label: "I did not understand the concept",
  },
] as const;

interface SelfReportTagModalProps {
  currentReason: string | null | undefined;
  isSaving: boolean;
  onSave: (reason: string | null) => Promise<void>;
}

export function SelfReportTagModal({
  currentReason,
  isSaving,
  onSave,
}: SelfReportTagModalProps) {
  const [selected, setSelected] = React.useState(currentReason ?? "");

  React.useEffect(() => {
    setSelected(currentReason ?? "");
  }, [currentReason]);

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 px-3 py-2">
      <span className="text-xs font-medium text-muted-foreground">
        Optional reflection:
      </span>
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        disabled={isSaving}
        aria-label="Self-reported mistake reason"
        className="rounded-md border border-input bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {MISTAKE_REASON_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={isSaving || selected === (currentReason ?? "")}
        onClick={() => void onSave(selected || null)}
      >
        {isSaving ? "Saving…" : "Save Tag"}
      </Button>
    </div>
  );
}
