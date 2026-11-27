"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  Copy,
  Download,
  Printer,
  RefreshCw,
} from "lucide-react";

import { RichMathText } from "@/components/common/MathRenderer";
import { FormulaBlock } from "@/components/notes/FormulaBlock";
import { NotesToc } from "@/components/notes/NotesToc";
import { RegenerateTopicDialog } from "@/components/notes/RegenerateTopicDialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatSubjectLabel } from "@/lib/api/examConfigs";
import {
  formatNoteType,
  type NoteDetailOut,
  type RegenerateNoteRequest,
} from "@/lib/api/notes";

interface NotesReaderProps {
  note: NoteDetailOut;
  isRegenerating: boolean;
  isUpdatingUnderstood: boolean;
  onRegenerate: (payload: RegenerateNoteRequest) => Promise<void>;
  onToggleUnderstood: () => Promise<void>;
}

function buildMarkdownExport(note: NoteDetailOut): string {
  const lines: string[] = [];
  lines.push(`# ${note.title}`);
  lines.push("");
  lines.push(
    `- **Type:** ${formatNoteType(note.note_type)} | **Version:** v${note.generation_version}`,
  );
  if (note.subject_code) {
    lines.push(`- **Subject:** ${formatSubjectLabel(note.subject_code)}`);
  }
  if (note.topic_name) {
    lines.push(`- **Topic:** ${note.topic_name}`);
  }
  lines.push("");
  if (note.content_json.summary) {
    lines.push("## Summary");
    lines.push(note.content_json.summary);
    lines.push("");
  }
  if (note.content_json.insufficient_evidence_message) {
    lines.push(`> **Notice:** ${note.content_json.insufficient_evidence_message}`);
    lines.push("");
  }
  for (const section of note.content_json.sections) {
    lines.push(`## ${section.title}`);
    lines.push("");
    for (const block of section.blocks) {
      const heading = block.title ? `### ${block.title}` : `### ${block.block_type}`;
      lines.push(`${heading} [${block.provenance}]`);
      lines.push(block.body);
      if (block.formula_latex) {
        lines.push("");
        lines.push(`$$${block.formula_latex}$$`);
      }
      if (block.source_refs.length > 0) {
        const refs = block.source_refs
          .map((r) => (r.page_number ? `Page ${r.page_number}` : "Source"))
          .join(", ");
        lines.push(`_Sources: ${refs}_`);
      }
      lines.push("");
    }
  }
  if (note.content_json.one_minute_recap) {
    lines.push("## 1-Minute Recap");
    lines.push(note.content_json.one_minute_recap);
  }
  return lines.join("\n");
}

export function NotesReader({
  note,
  isRegenerating,
  isUpdatingUnderstood,
  onRegenerate,
  onToggleUnderstood,
}: NotesReaderProps) {
  const [copied, setCopied] = React.useState(false);
  const [regenerateOpen, setRegenerateOpen] = React.useState(false);

  const markdownText = React.useMemo(() => buildMarkdownExport(note), [note]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdownText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable
    }
  };

  const handleDownload = () => {
    const blob = new Blob([markdownText], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    const safeName = note.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    anchor.download = `${safeName || "note"}-v${note.generation_version}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const isUnderstood = Boolean(note.understood_at);
  const sections = note.content_json.sections ?? [];
  const hasRecap = Boolean(note.content_json.one_minute_recap);

  return (
    <div className="space-y-6">
      <PageHeader
        title={note.title}
        description={`${formatNoteType(note.note_type)} · Version ${note.generation_version}${note.topic_name ? ` · ${note.topic_name}` : ""}`}
        actions={
          <div className="flex flex-wrap items-center gap-2 print:hidden">
            <Button
              type="button"
              variant={isUnderstood ? "default" : "outline"}
              size="sm"
              disabled={isUpdatingUnderstood}
              onClick={() => void onToggleUnderstood()}
            >
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              <span>{isUnderstood ? "Understood" : "Mark Understood"}</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isRegenerating}
              onClick={() => setRegenerateOpen(true)}
            >
              <RefreshCw
                className={`h-4 w-4 ${isRegenerating ? "animate-spin" : ""}`}
                aria-hidden="true"
              />
              <span>Regenerate</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleCopy()}
            >
              {copied ? (
                <Check className="h-4 w-4 text-emerald-600" aria-hidden="true" />
              ) : (
                <Copy className="h-4 w-4" aria-hidden="true" />
              )}
              <span>{copied ? "Copied" : "Copy"}</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleDownload}
            >
              <Download className="h-4 w-4" aria-hidden="true" />
              <span>Export .md</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => window.print()}
            >
              <Printer className="h-4 w-4" aria-hidden="true" />
              <span>Print</span>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href={`/documents/${encodeURIComponent(note.document_id)}`}>
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                <span>Document</span>
              </Link>
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="secondary">{formatNoteType(note.note_type)}</Badge>
        {note.subject_code ? (
          <Badge variant="outline">
            {formatSubjectLabel(note.subject_code)}
          </Badge>
        ) : null}
        <Badge
          variant={
            note.status === "ready"
              ? "success"
              : note.status === "insufficient_evidence"
                ? "warning"
                : "secondary"
          }
        >
          {note.status.replace(/_/g, " ")}
        </Badge>
        {note.model_name ? (
          <span className="text-muted-foreground">
            Generated by {note.model_name} ({note.prompt_version ?? "v1"})
          </span>
        ) : null}
      </div>

      {note.content_json.insufficient_evidence_message ? (
        <div
          role="status"
          className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-medium">Not enough verified source evidence</p>
            <p className="mt-0.5 text-xs">
              {note.content_json.insufficient_evidence_message}
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <aside className="lg:col-span-1">
          <div className="lg:sticky lg:top-6">
            <NotesToc sections={sections} hasRecap={hasRecap} />
          </div>
        </aside>

        <article className="space-y-6 lg:col-span-3">
          {note.content_json.summary ? (
            <Card>
              <CardHeader>
                <CardTitle>Overview</CardTitle>
              </CardHeader>
              <CardContent className="text-sm">
                <RichMathText text={note.content_json.summary} />
              </CardContent>
            </Card>
          ) : null}

          {sections.map((section, idx) => (
            <section
              key={section.key}
              id={`section-${section.key}`}
              className="scroll-mt-16 space-y-3"
            >
              <h2 className="border-b pb-2 text-lg font-semibold tracking-tight">
                {idx + 1}. {section.title}
              </h2>
              <div className="space-y-3">
                {section.blocks.map((block, bIdx) => (
                  <FormulaBlock
                    key={`${section.key}-${bIdx}`}
                    block={block}
                    fallbackDocumentId={note.document_id}
                  />
                ))}
              </div>
            </section>
          ))}

          {note.content_json.one_minute_recap ? (
            <Card id="section-one-minute-recap" className="border-primary/30">
              <CardHeader>
                <CardTitle>1-Minute Recap</CardTitle>
                <CardDescription>
                  High-yield points for quick final review.
                </CardDescription>
              </CardHeader>
              <CardContent className="text-sm">
                <RichMathText text={note.content_json.one_minute_recap} />
              </CardContent>
            </Card>
          ) : null}
        </article>
      </div>

      <RegenerateTopicDialog
        open={regenerateOpen}
        sections={sections}
        isRegenerating={isRegenerating}
        onClose={() => setRegenerateOpen(false)}
        onConfirm={async (payload) => {
          await onRegenerate(payload);
          setRegenerateOpen(false);
        }}
      />
    </div>
  );
}
