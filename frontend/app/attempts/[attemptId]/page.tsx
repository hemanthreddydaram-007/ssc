"use client";

import { useParams } from "next/navigation";

import { TestPlayerShell } from "@/components/test-player/TestPlayerShell";

export default function AttemptPlayerPage() {
  const params = useParams<{ attemptId: string }>();
  return <TestPlayerShell attemptId={params.attemptId} />;
}
