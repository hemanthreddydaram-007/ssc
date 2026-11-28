"use client";

import * as React from "react";
import { RefreshCw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { NoteSectionOut } from "@/lib/api/notes";

interface RegenerateTopicDialogProps {
  open: boolean;
  sections: readonly NoteSectionOut[];
  isRegenerating: boolean;
  onClose: () => void;
  onConfirm: (payload: {
    section_keys?: string[];
    custom_instruction?: string;
  }) => Promise<void>;
}

export function RegenerateTopicDialog({
  open,
  sections,
  isRegenerating,
  onClose,
  onConfirm,
}: RegenerateTopicDialogProps) {
  const [selectedKeys, setSelectedKeys] = React.useState<string[]>([]);
  const [instruction, setInstruction] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setSelectedKeys([]);
      setInstruction("");
    }
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isRegenerating) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, isRegenerating, onClose]);

  if (!open) {
    return null;
  }

  const toggleKey = (key: string) => {
    setSelectedKeys((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key],
    );
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await onConfirm({
      section_keys: selectedKeys.length > 0 ? selectedKeys : undefined,
      custom_instruction: instruction.trim() || undefined,
    });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="regenerate-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4 backdrop-blur-sm"
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2
              id="regenerate-dialog-title"
              className="text-lg font-semibold"
            >
              Regenerate Topic Note
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Rebuilds from stored facts and concepts without re-extracting the
              PDF.
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Close dialog"
            disabled={isRegenerating}
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {sections.length > 0 ? (
            <div>
              <p className="text-sm font-medium">
                Sections to regenerate{" "}
                <span className="text-xs font-normal text-muted-foreground">
                  (leave unchecked to regenerate all)
                </span>
              </p>
              <div className="mt-2 max-h-40 space-y-1.5 overflow-y-auto rounded-md border p-2.5">
                {sections.map((section) => (
                  <label
                    key={section.key}
                    className="flex cursor-pointer items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={selectedKeys.includes(section.key)}
                      onChange={() => toggleKey(section.key)}
                      disabled={isRegenerating}
                      className="h-4 w-4 rounded border-input"
                    />
                    <span>{section.title}</span>
                  </label>
                ))}
              </div>
            </div>
          ) : null}

          <div>
            <label
              htmlFor="regenerate-custom-instruction"
              className="block text-sm font-medium"
            >
              Optional focus instruction
            </label>
            <textarea
              id="regenerate-custom-instruction"
              rows={3}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              disabled={isRegenerating}
              placeholder="e.g. Add clearer step-by-step arithmetic examples or emphasize common traps"
              className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={isRegenerating}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isRegenerating}>
              <RefreshCw
                className={`h-4 w-4 ${isRegenerating ? "animate-spin" : ""}`}
                aria-hidden="true"
              />
              <span>{isRegenerating ? "Regenerating…" : "Regenerate"}</span>
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
