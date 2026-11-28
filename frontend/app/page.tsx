"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  FileUp,
  GraduationCap,
  Layers,
  ShieldCheck,
  Sparkles,
  Timer,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAuthToken } from "@/lib/api/auth";

const WORKFLOW_STEPS = [
  {
    step: "Step 1",
    title: "Upload PDF / PYQs",
    description:
      "Upload chapter PDFs, previous-year papers, scanned images, or pasted notes with page-by-page extraction and OCR.",
    icon: FileUp,
  },
  {
    step: "Step 2",
    title: "Extract Smart Notes & Concepts",
    description:
      "Turn source pages into structured Detailed Notes, Quick Revision sheets, formulas, and exam strategy guides.",
    icon: Sparkles,
  },
  {
    step: "Step 3",
    title: "Take Timed Mock Tests",
    description:
      "Practice extracted PYQs or source-grounded MCQs in Speed Challenge, Exam Simulation, or Learning Mode.",
    icon: ClipboardCheck,
  },
  {
    step: "Step 4",
    title: "Review Mistakes & Fix Weak Topics",
    description:
      "Diagnose accuracy vs speed traps per topic and launch targeted practice retests to turn weak areas strong.",
    icon: BarChart3,
  },
] as const;

const STUDY_MODES = [
  {
    title: "Speed Challenge",
    badge: "35s / question",
    description:
      "Server-enforced per-question countdowns with auto-advance train fast decision making under real SSC pressure.",
    icon: Zap,
  },
  {
    title: "Exam Simulation",
    badge: "Full mock timer",
    description:
      "Navigate freely across questions, mark items for review, apply negative marking, and review full solutions after submission.",
    icon: Timer,
  },
  {
    title: "Learning Mode",
    badge: "Instant explanations",
    description:
      "Check your answer and read source-grounded explanations immediately after each question, plus tag mistake reasons.",
    icon: Layers,
  },
  {
    title: "Source-Grounded Notes",
    badge: "Verified provenance",
    description:
      "Every note and fact clearly distinguishes extracted textbook content from AI explanations — no invented claims.",
    icon: BookOpen,
  },
] as const;

export default function HomePage() {
  const [hasToken, setHasToken] = React.useState(false);
  const [authChecked, setAuthChecked] = React.useState(false);

  React.useEffect(() => {
    setHasToken(Boolean(getAuthToken()));
    setAuthChecked(true);
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      {/* Sleek Top Navigation */}
      <header className="sticky top-0 z-30 border-b bg-card/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-2 px-3 sm:gap-4 sm:px-6 lg:px-8">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-2 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:gap-2.5"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <GraduationCap className="h-4 w-4" aria-hidden="true" />
            </span>
            <span>
              <span className="block whitespace-nowrap text-[13px] font-semibold leading-none sm:text-sm">
                AI Exam Coach
              </span>
              <span className="mt-0.5 hidden truncate text-[11px] text-muted-foreground sm:block">
                SSC &amp; Competitive Prep
              </span>
            </span>
          </Link>

          <nav
            aria-label="Overview navigation"
            className="hidden items-center gap-6 text-sm text-muted-foreground md:flex"
          >
            <a
              href="#how-it-works"
              className="transition-colors hover:text-foreground"
            >
              How It Works
            </a>
            <a
              href="#study-modes"
              className="transition-colors hover:text-foreground"
            >
              Exam Modes
            </a>
          </nav>

          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            {authChecked && hasToken ? (
              <>
                <Button asChild variant="ghost" size="sm">
                  <Link href="/library">Library</Link>
                </Button>
                <Button asChild size="sm">
                  <Link href="/dashboard">
                    <span className="sm:hidden">Dashboard</span>
                    <span className="hidden sm:inline">Open Your Dashboard</span>
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
              </>
            ) : (
              <>
                <Button asChild variant="ghost" size="sm">
                  <Link href="/login">Sign In</Link>
                </Button>
                <Button asChild size="sm">
                  <Link href="/register">
                    <span className="sm:hidden">Get Started</span>
                    <span className="hidden sm:inline">Create Free Account</span>
                  </Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero Section */}
        <section className="border-b bg-card/60">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:px-8">
            <div className="mx-auto max-w-3xl text-center">
              <Badge variant="secondary" className="mb-4 px-3 py-1 text-xs">
                SSC CHSL &amp; Competitive Exam Study Workspace
              </Badge>
              <h1 className="text-3xl font-bold tracking-tight sm:text-5xl">
                Turn your PDFs &amp; PYQs into smart notes, timed mocks, and
                topic mastery.
              </h1>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                AI Exam Coach turns your uploaded study PDFs and previous-year
                papers into source-grounded revision notes, realistic timed
                tests, and topic-level speed and accuracy coaching.
              </p>

              <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                {authChecked && hasToken ? (
                  <>
                    <Button asChild size="lg">
                      <Link href="/dashboard">
                        <span>Open Your Dashboard</span>
                        <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </Link>
                    </Button>
                    <Button asChild variant="outline" size="lg">
                      <Link href="/library">
                        <FileUp className="h-4 w-4" aria-hidden="true" />
                        <span>Upload Material</span>
                      </Link>
                    </Button>
                  </>
                ) : (
                  <>
                    <Button asChild size="lg">
                      <Link href="/register">
                        <span>Create Free Account</span>
                        <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </Link>
                    </Button>
                    <Button asChild variant="outline" size="lg">
                      <Link href="/login">Sign In</Link>
                    </Button>
                  </>
                )}
              </div>

              <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground sm:text-sm">
                <span className="inline-flex items-center gap-1.5">
                  <CheckCircle2
                    className="h-4 w-4 text-primary"
                    aria-hidden="true"
                  />
                  Private per-student library
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <ShieldCheck
                    className="h-4 w-4 text-primary"
                    aria-hidden="true"
                  />
                  Notes &amp; answers grounded in your PDFs
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Timer className="h-4 w-4 text-primary" aria-hidden="true" />
                  Speed Challenge, Exam &amp; Learning modes
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* How It Works in 4 Steps */}
        <section
          id="how-it-works"
          className="mx-auto max-w-6xl px-4 py-14 sm:px-6 lg:px-8"
        >
          <div className="mb-8 text-center">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              How It Works in 4 Steps
            </h2>
            <p className="mt-2 text-sm text-muted-foreground sm:text-base">
              A complete study loop from raw PDFs to faster, higher-accuracy
              mock scores.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {WORKFLOW_STEPS.map((item) => {
              const Icon = item.icon;
              return (
                <Card key={item.step} className="flex flex-col">
                  <CardHeader className="pb-3">
                    <div className="mb-2 flex items-center justify-between">
                      <Badge variant="outline">{item.step}</Badge>
                      <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                        <Icon className="h-4 w-4" aria-hidden="true" />
                      </span>
                    </div>
                    <CardTitle className="text-base">{item.title}</CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0 text-sm text-muted-foreground">
                    {item.description}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </section>

        {/* Exam Modes & Study Tools */}
        <section id="study-modes" className="border-t bg-card/50">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 lg:px-8">
            <div className="mb-8 text-center">
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                Built for Real Exam Speed &amp; Revision
              </h2>
              <p className="mt-2 text-sm text-muted-foreground sm:text-base">
                Switch between timed exam pressure and guided concept revision
                without leaving your workspace.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {STUDY_MODES.map((mode) => {
                const Icon = mode.icon;
                return (
                  <Card key={mode.title}>
                    <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                          <Icon className="h-4 w-4" aria-hidden="true" />
                        </span>
                        <div>
                          <CardTitle className="text-base">
                            {mode.title}
                          </CardTitle>
                          <CardDescription className="mt-1">
                            {mode.description}
                          </CardDescription>
                        </div>
                      </div>
                      <Badge variant="secondary" className="shrink-0">
                        {mode.badge}
                      </Badge>
                    </CardHeader>
                  </Card>
                );
              })}
            </div>
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
          <Card className="border-primary/30 bg-primary/5">
            <CardContent className="flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center">
              <div>
                <h2 className="text-lg font-semibold">
                  {authChecked && hasToken
                    ? "Your study workspace is ready."
                    : "Start organizing your exam prep in minutes."}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {authChecked && hasToken
                    ? "Jump back to your dashboard to upload PDFs, revise smart notes, or launch a timed practice test."
                    : "Create a free private account to upload your first PDF or previous-year paper."}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {authChecked && hasToken ? (
                  <Button asChild size="sm">
                    <Link href="/dashboard">
                      <span>Open Your Dashboard</span>
                      <ArrowRight className="h-4 w-4" aria-hidden="true" />
                    </Link>
                  </Button>
                ) : (
                  <>
                    <Button asChild variant="outline" size="sm">
                      <Link href="/login">Sign In</Link>
                    </Button>
                    <Button asChild size="sm">
                      <Link href="/register">Create Free Account</Link>
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        </section>
      </main>

      <footer className="border-t bg-card py-6 text-center text-xs text-muted-foreground">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 sm:flex-row sm:px-6 lg:px-8">
          <span>AI Exam Coach · Source-grounded competitive exam workspace</span>
          <div className="flex items-center gap-4">
            <Link href="/login" className="hover:text-foreground hover:underline">
              Sign In
            </Link>
            <Link
              href="/register"
              className="hover:text-foreground hover:underline"
            >
              Register
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
