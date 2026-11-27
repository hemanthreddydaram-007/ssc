"use client";

import * as React from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

import { cn } from "@/lib/utils/cn";

interface MathRendererProps {
  latex: string;
  displayMode?: boolean;
  className?: string;
}

/**
 * Safely renders a LaTeX expression using KaTeX DOM rendering (`trust: false`,
 * `throwOnError: false`) without `dangerouslySetInnerHTML`.
 */
export function MathRenderer({
  latex,
  displayMode = false,
  className,
}: MathRendererProps) {
  const containerRef = React.useRef<HTMLSpanElement>(null);

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    try {
      katex.render(latex, el, {
        displayMode,
        throwOnError: false,
        strict: false,
        trust: false,
      });
    } catch {
      el.textContent = latex;
    }
  }, [latex, displayMode]);

  return (
    <span
      ref={containerRef}
      className={cn(
        displayMode
          ? "my-2 block overflow-x-auto py-1 text-center"
          : "inline-block align-middle",
        className,
      )}
    >
      {latex}
    </span>
  );
}

type TextSegment =
  | { kind: "text"; value: string }
  | { kind: "inline_math"; value: string }
  | { kind: "block_math"; value: string };

function tokenizeMathSegments(input: string): TextSegment[] {
  const segments: TextSegment[] = [];
  const pattern = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null = pattern.exec(input);

  while (match !== null) {
    if (match.index > lastIndex) {
      segments.push({
        kind: "text",
        value: input.slice(lastIndex, match.index),
      });
    }
    if (match[1] !== undefined) {
      segments.push({ kind: "block_math", value: match[1].trim() });
    } else if (match[2] !== undefined) {
      segments.push({ kind: "inline_math", value: match[2].trim() });
    }
    lastIndex = pattern.lastIndex;
    match = pattern.exec(input);
  }

  if (lastIndex < input.length) {
    segments.push({ kind: "text", value: input.slice(lastIndex) });
  }
  return segments;
}

/**
 * Renders plain prose with embedded `$...$` / `$$...$$` math tokens safely.
 */
export function RichMathText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const segments = React.useMemo(() => tokenizeMathSegments(text), [text]);

  return (
    <div className={cn("whitespace-pre-line leading-relaxed", className)}>
      {segments.map((seg, idx) => {
        if (seg.kind === "text") {
          return <React.Fragment key={idx}>{seg.value}</React.Fragment>;
        }
        if (seg.kind === "block_math") {
          return (
            <MathRenderer key={idx} latex={seg.value} displayMode />
          );
        }
        return <MathRenderer key={idx} latex={seg.value} />;
      })}
    </div>
  );
}
