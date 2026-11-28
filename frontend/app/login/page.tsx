"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Eye,
  EyeOff,
  GraduationCap,
  LogIn,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { loginUser } from "@/lib/api/auth";

function getSafeRedirectTarget(rawNext: string | null): string {
  if (!rawNext || !rawNext.startsWith("/") || rawNext.startsWith("//")) {
    return "/dashboard";
  }
  return rawNext;
}

const WORKSPACE_HIGHLIGHTS = [
  "Upload SSC & competitive exam PDFs, PYQs, images, or pasted notes into your private library.",
  "Generate source-grounded Detailed Notes, Quick Revision sheets, and practice MCQs.",
  "Train with Speed Challenge, Exam Simulation, and Learning Mode timers plus weak-topic analytics.",
] as const;

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = getSafeRedirectTarget(searchParams.get("next"));

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await loginUser({ email: email.trim(), password });
      router.replace(nextPath);
    } catch (error) {
      if (error instanceof TypeError) {
        setErrorMessage(
          "Unable to reach the server right now. If it is waking up on free hosting (~30–50s), wait a moment and try again.",
        );
      } else {
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to sign in.",
        );
      }
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-[82vh] flex-col justify-center py-4">
      <div className="mb-4">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          <span>Back to Overview</span>
        </Link>
      </div>

      <div className="grid grid-cols-1 items-center gap-6 lg:grid-cols-12">
        {/* Product Overview Strip */}
        <div className="rounded-lg border bg-card p-6 shadow-sm lg:col-span-5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <GraduationCap className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-semibold leading-none">AI Exam Coach</p>
              <p className="mt-1 text-xs text-muted-foreground">
                SSC &amp; Competitive Exam Prep
              </p>
            </div>
          </div>

          <h1 className="mt-4 text-lg font-semibold tracking-tight">
            Your source-grounded study &amp; mock-test workspace
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Sign in to continue studying from your private uploads and test
            history.
          </p>

          <ul className="mt-4 space-y-2.5 text-sm text-muted-foreground">
            {WORKSPACE_HIGHLIGHTS.map((bullet) => (
              <li key={bullet} className="flex items-start gap-2">
                <CheckCircle2
                  className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                  aria-hidden="true"
                />
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Sign-in Card */}
        <div className="lg:col-span-7">
          <Card className="mx-auto w-full max-w-md">
            <CardHeader className="space-y-2 text-center">
              <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <GraduationCap className="h-5 w-5" aria-hidden="true" />
              </div>
              <CardTitle className="text-xl">Sign in to AI Exam Coach</CardTitle>
              <CardDescription>
                Access your private study materials, notes, and timed tests.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label
                    htmlFor="login-email"
                    className="block text-sm font-medium"
                  >
                    Email
                  </label>
                  <input
                    id="login-email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={isSubmitting}
                    placeholder="student@example.com"
                    className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>

                <div>
                  <label
                    htmlFor="login-password"
                    className="block text-sm font-medium"
                  >
                    Password
                  </label>
                  <div className="relative mt-1.5">
                    <input
                      id="login-password"
                      type={showPassword ? "text" : "password"}
                      required
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      disabled={isSubmitting}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 pr-10 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((prev) => !prev)}
                      aria-label={
                        showPassword ? "Hide password" : "Show password"
                      }
                      aria-pressed={showPassword}
                      disabled={isSubmitting}
                      className="absolute inset-y-0 right-0 flex items-center rounded-r-md px-3 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {showPassword ? (
                        <EyeOff className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <Eye className="h-4 w-4" aria-hidden="true" />
                      )}
                    </button>
                  </div>
                </div>

                {errorMessage ? (
                  <div
                    role="alert"
                    className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
                  >
                    <AlertCircle
                      className="mt-0.5 h-4 w-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span>{errorMessage}</span>
                  </div>
                ) : null}

                <Button type="submit" className="w-full" disabled={isSubmitting}>
                  <LogIn className="h-4 w-4" aria-hidden="true" />
                  <span>{isSubmitting ? "Signing in…" : "Sign In"}</span>
                </Button>

                <p className="text-center text-xs text-muted-foreground">
                  Need an account?{" "}
                  <Link
                    href={`/register${nextPath !== "/dashboard" ? `?next=${encodeURIComponent(nextPath)}` : ""}`}
                    className="font-medium text-primary hover:underline"
                  >
                    Create student account
                  </Link>
                </p>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <React.Suspense
      fallback={
        <div className="py-12 text-center text-sm text-muted-foreground">
          Loading sign in…
        </div>
      }
    >
      <LoginForm />
    </React.Suspense>
  );
}
