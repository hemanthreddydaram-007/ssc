"use client";

import * as React from "react";

import { getAuthToken } from "@/lib/api/auth";
import { handleUnauthorizedRedirect } from "@/lib/api/client";
import { getDocumentAssetUrl } from "@/lib/api/documents";

interface AuthAssetImageProps {
  documentId: string;
  assetId: string;
  alt: string;
  className?: string;
  fallbackText?: string;
}

/**
 * Fetches private document asset images with Bearer auth and renders via blob URL,
 * revoking the object URL on unmount or dependency change.
 */
export function AuthAssetImage({
  documentId,
  assetId,
  alt,
  className,
  fallbackText = "Unable to load protected asset preview.",
}: AuthAssetImageProps) {
  const [objectUrl, setObjectUrl] = React.useState<string | null>(null);
  const [failed, setFailed] = React.useState(false);

  const src = getDocumentAssetUrl(documentId, assetId);

  React.useEffect(() => {
    const controller = new AbortController();
    let createdUrl: string | null = null;
    setFailed(false);
    setObjectUrl(null);

    const token = getAuthToken();
    const headers: HeadersInit | undefined = token
      ? { Authorization: `Bearer ${token}` }
      : undefined;

    fetch(src, {
      method: "GET",
      headers,
      signal: controller.signal,
      cache: "no-store",
    })
      .then(async (res) => {
        if (res.status === 401) {
          handleUnauthorizedRedirect();
          throw new Error("Unauthorized");
        }
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const blob = await res.blob();
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setFailed(true);
      });

    return () => {
      controller.abort();
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [src]);

  if (failed) {
    return (
      <div className="flex h-36 items-center justify-center p-3 text-center text-xs text-muted-foreground">
        {fallbackText}
      </div>
    );
  }

  if (!objectUrl) {
    return (
      <div className="flex h-36 items-center justify-center p-3 text-center text-xs text-muted-foreground">
        Loading protected diagram…
      </div>
    );
  }

  return (
    /* eslint-disable-next-line @next/next/no-img-element */
    <img src={objectUrl} alt={alt} className={className} />
  );
}
