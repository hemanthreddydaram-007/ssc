"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  GraduationCap,
  LogIn,
  Menu,
  Settings,
  UserCheck,
  X,
} from "lucide-react";

import { NAV_ITEMS, type NavItem } from "@/components/layout/nav-items";
import { Button } from "@/components/ui/button";
import { getAuthToken } from "@/lib/api/auth";
import { fetchBackendHealth, type HealthCheckResult } from "@/lib/api/health";
import { cn } from "@/lib/utils/cn";
import {
  applyDocumentPreferenceFlags,
  loadPreferences,
} from "@/lib/utils/preferences";

interface AppShellProps {
  children: React.ReactNode;
}

function isNavItemActive(pathname: string, item: NavItem): boolean {
  if (pathname === item.href || pathname.startsWith(`${item.href}/`)) {
    return true;
  }
  if (item.matchPrefixes) {
    return item.matchPrefixes.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    );
  }
  return false;
}

function SidebarNav({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <nav
      aria-label="Primary navigation"
      className="flex-1 space-y-1 overflow-y-auto px-3 py-4"
    >
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = isNavItemActive(pathname, item);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex items-start gap-3 rounded-md px-3 py-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium leading-tight">
                {item.label}
              </span>
              {item.caption ? (
                <span
                  className={cn(
                    "mt-0.5 block truncate text-[11px] leading-tight",
                    isActive
                      ? "text-primary-foreground/85"
                      : "text-muted-foreground/85",
                  )}
                >
                  {item.caption}
                </span>
              ) : null}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

function SidebarFooterStatus({
  hasToken,
  health,
  onNavigate,
}: {
  hasToken: boolean;
  health: HealthCheckResult | null;
  onNavigate?: () => void;
}) {
  const statusIndicator = (() => {
    if (!health) {
      return {
        dotClass: "bg-muted-foreground/50",
        label: "Checking server…",
      };
    }
    if (health.kind === "ok") {
      return {
        dotClass: "bg-emerald-500",
        label: "Server connected",
      };
    }
    if (health.kind === "degraded") {
      return {
        dotClass: "bg-amber-500",
        label: "Server degraded",
      };
    }
    return {
      dotClass: "bg-amber-500",
      label: "Server waking up…",
    };
  })();

  const isDevMode =
    health?.kind === "ok" && health.payload.auth_mode === "dev_header";

  return (
    <div className="space-y-2.5 border-t px-4 py-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-2 text-muted-foreground">
          <span
            className={cn("h-2 w-2 shrink-0 rounded-full", statusIndicator.dotClass)}
            aria-hidden="true"
          />
          <span>{statusIndicator.label}</span>
        </span>
        <Link
          href="/settings"
          onClick={onNavigate}
          className="font-medium text-muted-foreground hover:text-foreground hover:underline"
        >
          Status
        </Link>
      </div>

      <div className="flex items-center justify-between gap-2 rounded-md border bg-muted/40 px-2.5 py-2">
        {hasToken ? (
          <>
            <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
              <UserCheck className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
              <span>Signed in</span>
            </span>
            <Link
              href="/settings"
              onClick={onNavigate}
              className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
            >
              <Settings className="h-3 w-3" aria-hidden="true" />
              <span>Account</span>
            </Link>
          </>
        ) : isDevMode ? (
          <>
            <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
              <UserCheck className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
              <span>Local mode</span>
            </span>
            <Link
              href="/settings"
              onClick={onNavigate}
              className="font-medium text-primary hover:underline"
            >
              Account
            </Link>
          </>
        ) : (
          <>
            <span className="text-muted-foreground">Not signed in</span>
            <Link
              href="/login"
              onClick={onNavigate}
              className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
            >
              <LogIn className="h-3 w-3" aria-hidden="true" />
              <span>Sign In</span>
            </Link>
          </>
        )}
      </div>

      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <Link
          href="/"
          onClick={onNavigate}
          className="hover:text-foreground hover:underline"
        >
          Overview Page
        </Link>
        <span>SSC Prep</span>
      </div>
    </div>
  );
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [hasToken, setHasToken] = React.useState(false);
  const [health, setHealth] = React.useState<HealthCheckResult | null>(null);

  const isLandingPage = pathname === "/";
  const isDistractionFreePlayer =
    pathname.startsWith("/attempts/") && !pathname.endsWith("/results");
  const isAuthPage =
    pathname.startsWith("/login") || pathname.startsWith("/register");
  const showWorkspaceShell =
    !isLandingPage && !isDistractionFreePlayer && !isAuthPage;

  React.useEffect(() => {
    applyDocumentPreferenceFlags(loadPreferences());
  }, []);

  React.useEffect(() => {
    setMobileOpen(false);
    setHasToken(Boolean(getAuthToken()));
  }, [pathname]);

  React.useEffect(() => {
    const syncAuth = () => setHasToken(Boolean(getAuthToken()));
    window.addEventListener("storage", syncAuth);
    return () => window.removeEventListener("storage", syncAuth);
  }, []);

  React.useEffect(() => {
    if (!showWorkspaceShell) {
      return;
    }
    const controller = new AbortController();
    fetchBackendHealth(controller.signal)
      .then(setHealth)
      .catch(() => {
        // Ignore aborted checks
      });
    return () => controller.abort();
  }, [showWorkspaceShell]);

  React.useEffect(() => {
    if (!mobileOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mobileOpen]);

  if (isLandingPage) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        {children}
      </div>
    );
  }

  if (isDistractionFreePlayer || isAuthPage) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <main className="mx-auto max-w-5xl px-4 py-4 sm:px-6 sm:py-6">
          {children}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Desktop sidebar */}
      <aside className="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:flex lg:w-64 lg:flex-col lg:border-r lg:bg-card">
        <Link
          href="/dashboard"
          className="flex h-16 items-center gap-2.5 border-b px-5 transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <GraduationCap className="h-4 w-4" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-none">AI Exam Coach</p>
            <p className="mt-1 text-xs text-muted-foreground">
              SSC CHSL &amp; Exam Prep
            </p>
          </div>
        </Link>
        <SidebarNav pathname={pathname} />
        <SidebarFooterStatus hasToken={hasToken} health={health} />
      </aside>

      {/* Mobile header */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-card px-4 lg:hidden">
        <Link
          href="/dashboard"
          className="flex items-center gap-2 rounded-md font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <GraduationCap className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="text-sm">AI Exam Coach</span>
        </Link>
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav-drawer"
          onClick={() => setMobileOpen((prev) => !prev)}
        >
          {mobileOpen ? (
            <X className="h-5 w-5" aria-hidden="true" />
          ) : (
            <Menu className="h-5 w-5" aria-hidden="true" />
          )}
        </Button>
      </header>

      {/* Mobile navigation drawer */}
      {mobileOpen ? (
        <div
          id="mobile-nav-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation menu"
          className="fixed inset-0 z-40 flex lg:hidden"
        >
          <div
            className="fixed inset-0 bg-foreground/40 backdrop-blur-sm"
            aria-hidden="true"
            onClick={() => setMobileOpen(false)}
          />
          <div className="relative z-10 flex w-72 max-w-[85vw] flex-col border-r bg-card shadow-xl">
            <div className="flex h-14 items-center justify-between border-b px-4">
              <div className="flex items-center gap-2 font-semibold">
                <GraduationCap className="h-4 w-4 text-primary" aria-hidden="true" />
                <span className="text-sm">AI Exam Coach</span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Close navigation menu"
                onClick={() => setMobileOpen(false)}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            <SidebarNav
              pathname={pathname}
              onNavigate={() => setMobileOpen(false)}
            />
            <SidebarFooterStatus
              hasToken={hasToken}
              health={health}
              onNavigate={() => setMobileOpen(false)}
            />
          </div>
        </div>
      ) : null}

      {/* Main content area */}
      <div className="lg:pl-64">
        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
