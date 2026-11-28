"use client";

import * as React from "react";

interface UseKeyboardNavOptions {
  enabled: boolean;
  optionKeys: readonly string[];
  onSelectOption: (optionKey: string) => void;
  onNext: () => void;
  onPrevious?: () => void;
  onToggleReview?: () => void;
  onSkip?: () => void;
}

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") {
    return true;
  }
  if (target.isContentEditable) {
    return true;
  }
  return Boolean(target.closest('[role="dialog"]'));
}

export function useKeyboardNav({
  enabled,
  optionKeys,
  onSelectOption,
  onNext,
  onPrevious,
  onToggleReview,
  onSkip,
}: UseKeyboardNavOptions) {
  React.useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (isEditableElement(event.target)) {
        return;
      }

      const key = event.key;
      const upper = key.toUpperCase();

      if (/^[1-4]$/.test(key)) {
        const idx = Number(key) - 1;
        const opt = optionKeys[idx];
        if (opt) {
          event.preventDefault();
          onSelectOption(opt);
        }
        return;
      }

      const matchedOption = optionKeys.find(
        (opt) => opt.toUpperCase() === upper,
      );
      if (matchedOption) {
        event.preventDefault();
        onSelectOption(matchedOption);
        return;
      }

      if (key === "ArrowRight") {
        event.preventDefault();
        onNext();
        return;
      }

      if (key === "ArrowLeft" && onPrevious) {
        event.preventDefault();
        onPrevious();
        return;
      }

      if (upper === "R" && onToggleReview) {
        event.preventDefault();
        onToggleReview();
        return;
      }

      if (upper === "S" && onSkip) {
        event.preventDefault();
        onSkip();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    enabled,
    optionKeys,
    onSelectOption,
    onNext,
    onPrevious,
    onToggleReview,
    onSkip,
  ]);
}
