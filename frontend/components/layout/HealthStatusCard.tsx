"use client";

import * as React from "react";
import { Activity, RefreshCw } from "lucide-react";

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
  fetchBackendHealth,
  getApiBaseUrl,
  type HealthCheckResult,
} from "@/lib/api/health";

export function HealthStatusCard() {
  const [result, setResult] = React.useState<HealthCheckResult | null>(null);
  const [isChecking, setIsChecking] = React.useState<boolean>(true);
  const apiBaseUrl = getApiBaseUrl();

  const runCheck = React.useCallback(async (signal?: AbortSignal) => {
    setIsChecking(true);
    try {
      const next = await fetchBackendHealth(signal);
      setResult(next);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setResult({
        kind: "unreachable",
        errorMessage: "Failed to check backend health",
      });
    } finally {
      setIsChecking(false);
    }
  }, []);

  React.useEffect(() => {
    const controller = new AbortController();
    void runCheck(controller.signal);
    return () => controller.abort();
  }, [runCheck]);

  const badge = (() => {
    if (isChecking && !result) {
      return <Badge variant="secondary">Checking…</Badge>;
    }
    if (!result || result.kind === "unreachable") {
      return <Badge variant="destructive">Unreachable</Badge>;
    }
    if (result.kind === "degraded") {
      return <Badge variant="warning">Degraded</Badge>;
    }
    return <Badge variant="success">Connected</Badge>;
  })();

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
            <CardTitle>Backend API Health</CardTitle>
            {badge}
          </div>
          <CardDescription>
            Live status from <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{apiBaseUrl}/health</code>
          </CardDescription>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void runCheck()}
          disabled={isChecking}
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isChecking ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          <span>{isChecking ? "Checking" : "Refresh"}</span>
        </Button>
      </CardHeader>
      <CardContent>
        {result === null ? (
          <p className="text-sm text-muted-foreground" aria-live="polite">
            Querying backend health endpoint…
          </p>
        ) : result.kind === "unreachable" ? (
          <div
            role="status"
            aria-live="polite"
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
          >
            <p className="font-medium">Backend service is unreachable.</p>
            <p className="mt-1 text-xs">{result.errorMessage}</p>
          </div>
        ) : (
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs font-medium text-muted-foreground">
                Service Status
              </dt>
              <dd className="mt-1 font-medium capitalize">
                {result.payload.status} (HTTP {result.httpStatus})
              </dd>
            </div>
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs font-medium text-muted-foreground">
                Database
              </dt>
              <dd className="mt-1 font-medium capitalize">
                {result.payload.database}
              </dd>
            </div>
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs font-medium text-muted-foreground">
                Environment
              </dt>
              <dd className="mt-1 font-medium">{result.payload.environment}</dd>
            </div>
            <div className="rounded-md border bg-muted/40 p-3">
              <dt className="text-xs font-medium text-muted-foreground">
                Version
              </dt>
              <dd className="mt-1 font-medium">{result.payload.version}</dd>
            </div>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
