"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { TestBuilderForm } from "@/components/test-player/TestBuilderForm";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { listDocuments, type DocumentItem } from "@/lib/api/documents";
import { listExamConfigs, type ExamConfig } from "@/lib/api/examConfigs";
import {
  listAllTopics,
  listSubjects,
  type SubjectOut,
  type TopicSummaryOut,
} from "@/lib/api/knowledge";

function NewTestContent() {
  const searchParams = useSearchParams();

  const initialQuestionIds = React.useMemo(() => {
    const raw = searchParams.get("question_ids");
    return raw ? raw.split(",").filter(Boolean) : [];
  }, [searchParams]);

  const initialDocumentId = searchParams.get("document_id") ?? "";
  const initialSubjectCode = searchParams.get("subject_code") ?? "";
  const initialTopicId = searchParams.get("topic_id") ?? "";

  const [examConfigs, setExamConfigs] = React.useState<ExamConfig[]>([]);
  const [documents, setDocuments] = React.useState<DocumentItem[]>([]);
  const [subjects, setSubjects] = React.useState<SubjectOut[]>([]);
  const [topics, setTopics] = React.useState<TopicSummaryOut[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      listExamConfigs(controller.signal).catch(() => [] as ExamConfig[]),
      listDocuments({ limit: 100 }, controller.signal)
        .then((r) => r.items)
        .catch(() => [] as DocumentItem[]),
      listSubjects(controller.signal).catch(() => [] as SubjectOut[]),
      listAllTopics(undefined, controller.signal)
        .then((r) => r.items)
        .catch(() => [] as TopicSummaryOut[]),
    ])
      .then(([cfgs, docs, subs, tops]) => {
        setExamConfigs(cfgs);
        setDocuments(docs);
        setSubjects(subs);
        setTopics(tops);
      })
      .finally(() => setIsLoading(false));

    return () => controller.abort();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Test Builder"
        description="Configure questions, timer mode, and marking rules before starting a timed attempt."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/tests">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              <span>Back to Tests</span>
            </Link>
          </Button>
        }
      />

      {isLoading ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Loading test configuration options…
          </CardContent>
        </Card>
      ) : (
        <TestBuilderForm
          examConfigs={examConfigs}
          documents={documents}
          subjects={subjects}
          topics={topics}
          initialQuestionIds={initialQuestionIds}
          initialDocumentId={initialDocumentId}
          initialSubjectCode={initialSubjectCode}
          initialTopicId={initialTopicId}
        />
      )}
    </div>
  );
}

export default function NewTestPage() {
  return (
    <React.Suspense
      fallback={
        <div className="py-10 text-center text-sm text-muted-foreground">
          Loading test builder…
        </div>
      }
    >
      <NewTestContent />
    </React.Suspense>
  );
}
