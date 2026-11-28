"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  LogIn,
  LogOut,
  RotateCcw,
  Trash2,
  User,
  UserPlus,
} from "lucide-react";

import { HealthStatusCard } from "@/components/layout/HealthStatusCard";
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
import {
  clearAuthToken,
  getAuthToken,
  getCurrentAuthUser,
  type AuthUserOut,
} from "@/lib/api/auth";
import {
  formatExamName,
  listExamConfigs,
  type ExamConfig,
} from "@/lib/api/examConfigs";
import { getApiBaseUrl } from "@/lib/api/health";
import {
  clampSpeedChallengeSeconds,
  clearCustomAiKey,
  loadCustomAiKey,
  loadPreferences,
  resetPreferences,
  saveCustomAiKey,
  savePreferences,
  type UserPreferences,
} from "@/lib/utils/preferences";

const TIMER_PRESETS = [15, 25, 35, 45, 60] as const;

export default function SettingsPage() {
  const router = useRouter();
  const apiBaseUrl = getApiBaseUrl();
  const [examConfigs, setExamConfigs] = React.useState<ExamConfig[]>([]);
  const [prefs, setPrefs] = React.useState<UserPreferences>(() =>
    loadPreferences(),
  );
  const [savedNotice, setSavedNotice] = React.useState<string | null>(null);
  const [customAiKey, setCustomAiKey] = React.useState("");
  const [showCustomKey, setShowCustomKey] = React.useState(false);
  const [customKeyNotice, setCustomKeyNotice] = React.useState<string | null>(
    null,
  );
  const [authUser, setAuthUser] = React.useState<AuthUserOut | null>(null);
  const [hasToken, setHasToken] = React.useState(false);

  React.useEffect(() => {
    setPrefs(loadPreferences());
    setCustomAiKey(loadCustomAiKey());
    setHasToken(Boolean(getAuthToken()));
    const controller = new AbortController();
    listExamConfigs(controller.signal)
      .then(setExamConfigs)
      .catch(() => setExamConfigs([]));
    getCurrentAuthUser(controller.signal)
      .then(setAuthUser)
      .catch(() => setAuthUser(null));
    return () => controller.abort();
  }, []);

  const handleSave = (event: React.FormEvent) => {
    event.preventDefault();
    const saved = savePreferences(prefs);
    setPrefs(saved);
    setSavedNotice("Preferences saved locally.");
  };

  const handleReset = () => {
    const defaults = resetPreferences();
    setPrefs(defaults);
    setSavedNotice("Reset to default preferences.");
  };

  const handleSignOut = () => {
    clearAuthToken();
    setHasToken(false);
    setAuthUser(null);
    router.push("/login");
  };

  const handleSaveCustomKey = (event: React.FormEvent) => {
    event.preventDefault();
    const saved = saveCustomAiKey(customAiKey);
    setCustomAiKey(saved);
    setCustomKeyNotice(
      saved.length > 0
        ? "Personal AI key saved in this browser and sent automatically on AI tasks."
        : "Cleared personal AI key — requests will use the shared server key.",
    );
  };

  const handleClearCustomKey = () => {
    clearCustomAiKey();
    setCustomAiKey("");
    setCustomKeyNotice(
      "Personal AI key removed from this browser.",
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Account session, study preferences, Speed Challenge defaults, and backend health."
      />

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <User className="h-4 w-4 text-primary" aria-hidden="true" />
              <CardTitle>Account &amp; Authentication</CardTitle>
              {authUser ? (
                <Badge variant="outline">{authUser.auth_mode}</Badge>
              ) : null}
            </div>
            <CardDescription>
              Active student identity used for private uploads, notes, and test
              history.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {hasToken ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleSignOut}
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
                <span>Sign Out</span>
              </Button>
            ) : (
              <>
                <Button asChild variant="outline" size="sm">
                  <Link href="/login">
                    <LogIn className="h-4 w-4" aria-hidden="true" />
                    <span>Sign In</span>
                  </Link>
                </Button>
                <Button asChild size="sm">
                  <Link href="/register">
                    <UserPlus className="h-4 w-4" aria-hidden="true" />
                    <span>Register</span>
                  </Link>
                </Button>
              </>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {authUser ? (
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div className="min-w-0 rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Display Name
                </dt>
                <dd className="mt-1 break-words font-medium">
                  {authUser.display_name}
                </dd>
              </div>
              <div className="min-w-0 rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Email
                </dt>
                <dd className="mt-1 break-words [overflow-wrap:anywhere] font-medium">
                  {authUser.email ?? "Local development profile"}
                </dd>
              </div>
              <div className="min-w-0 rounded-md border bg-muted/40 p-3">
                <dt className="text-xs font-medium text-muted-foreground">
                  Auth Mode
                </dt>
                <dd className="mt-1 font-mono text-xs">{authUser.auth_mode}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">
              Not signed in with a JWT account. Sign in or register if your
              backend requires JWT authentication.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Study &amp; Accessibility Preferences</CardTitle>
          <CardDescription>
            Saved in your browser and applied automatically when uploading
            materials or building timed tests.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSave} className="space-y-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="pref-exam-code"
                  className="block text-sm font-medium"
                >
                  Default Exam Pack
                </label>
                <select
                  id="pref-exam-code"
                  value={prefs.default_exam_code}
                  onChange={(e) => {
                    setPrefs((p) => ({
                      ...p,
                      default_exam_code: e.target.value,
                    }));
                    setSavedNotice(null);
                  }}
                  className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {examConfigs.length > 0 ? (
                    examConfigs.map((cfg) => (
                      <option key={cfg.id} value={cfg.exam_code}>
                        {formatExamName(cfg.name)}
                      </option>
                    ))
                  ) : (
                    <option value="ssc_chsl_tier_1">SSC CHSL Tier 1</option>
                  )}
                </select>
              </div>

              <div>
                <label
                  htmlFor="pref-speed-seconds"
                  className="block text-sm font-medium"
                >
                  Default Speed Challenge Timer (seconds)
                </label>
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  {TIMER_PRESETS.map((sec) => (
                    <Button
                      key={sec}
                      type="button"
                      size="sm"
                      variant={
                        prefs.default_speed_challenge_seconds === sec
                          ? "default"
                          : "outline"
                      }
                      onClick={() => {
                        setPrefs((p) => ({
                          ...p,
                          default_speed_challenge_seconds: sec,
                        }));
                        setSavedNotice(null);
                      }}
                    >
                      {sec}s
                    </Button>
                  ))}
                  <input
                    id="pref-speed-seconds"
                    type="number"
                    min={5}
                    max={300}
                    value={prefs.default_speed_challenge_seconds}
                    onChange={(e) => {
                      setPrefs((p) => ({
                        ...p,
                        default_speed_challenge_seconds:
                          clampSpeedChallengeSeconds(e.target.value),
                      }));
                      setSavedNotice(null);
                    }}
                    className="w-20 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-2.5 border-t pt-4">
              <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                <input
                  type="checkbox"
                  checked={prefs.reduced_motion}
                  onChange={(e) => {
                    setPrefs((p) => ({
                      ...p,
                      reduced_motion: e.target.checked,
                    }));
                    setSavedNotice(null);
                  }}
                  className="h-4 w-4 rounded border-input"
                />
                <span>
                  Reduce animations and transitions across the workspace
                </span>
              </label>

              <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                <input
                  type="checkbox"
                  checked={prefs.compact_mode}
                  onChange={(e) => {
                    setPrefs((p) => ({
                      ...p,
                      compact_mode: e.target.checked,
                    }));
                    setSavedNotice(null);
                  }}
                  className="h-4 w-4 rounded border-input"
                />
                <span>Use compact card spacing</span>
              </label>
            </div>

            {savedNotice ? (
              <div
                role="status"
                aria-live="polite"
                className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"
              >
                <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{savedNotice}</span>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleReset}
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Reset Defaults</span>
              </Button>
              <Button type="submit" size="sm">
                Save Preferences
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card id="custom-ai-key">
        <CardHeader>
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-primary" aria-hidden="true" />
            <CardTitle>Personal AI Key (Optional Quota Fallback)</CardTitle>
            {customAiKey.trim().length > 0 ? (
              <Badge variant="success">Active</Badge>
            ) : (
              <Badge variant="secondary">Using Server Default</Badge>
            )}
          </div>
          <CardDescription>
            If the shared free-tier AI quota reaches its daily limit, paste your
            own free Google AI Studio key below. It stays in your browser&apos;s
            local storage and is never saved to the server database.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSaveCustomKey} className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative min-w-0 flex-1">
                <label htmlFor="custom-ai-key-input" className="sr-only">
                  Personal Google Gemini API key
                </label>
                <input
                  id="custom-ai-key-input"
                  type={showCustomKey ? "text" : "password"}
                  autoComplete="off"
                  value={customAiKey}
                  onChange={(e) => {
                    setCustomAiKey(e.target.value);
                    setCustomKeyNotice(null);
                  }}
                  placeholder="Paste your free key from aistudio.google.com/apikey"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 pr-10 font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
                <button
                  type="button"
                  onClick={() => setShowCustomKey((prev) => !prev)}
                  aria-label={showCustomKey ? "Hide API key" : "Show API key"}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showCustomKey ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button type="submit" size="sm">
                  Save Key
                </Button>
                {customAiKey.trim().length > 0 ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleClearCustomKey}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>Remove</span>
                  </Button>
                ) : null}
              </div>
            </div>

            {customKeyNotice ? (
              <p
                role="status"
                aria-live="polite"
                className="text-xs font-medium text-emerald-700"
              >
                {customKeyNotice}
              </p>
            ) : null}

            <p className="text-xs text-muted-foreground">
              Get a free key in ~10 seconds from{" "}
              <a
                href="https://aistudio.google.com/apikey"
                target="_blank"
                rel="noreferrer"
                className="font-medium text-primary hover:underline"
              >
                Google AI Studio
              </a>
              . Requests still try multiple Gemini Flash models automatically
              before failing.
            </p>
          </form>
        </CardContent>
      </Card>

      <HealthStatusCard />

      <Card>
        <CardHeader>
          <CardTitle>Frontend Runtime Configuration</CardTitle>
          <CardDescription>
            Active non-secret runtime settings for the web application.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs font-medium text-muted-foreground">
                API Base URL
              </dt>
              <dd className="mt-1 font-mono text-xs">{apiBaseUrl}</dd>
            </div>
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs font-medium text-muted-foreground">
                Configured Default Exam
              </dt>
              <dd className="mt-1 font-medium">{prefs.default_exam_code}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
