"use client";

import { useEffect, useState } from "react";

import LoadingOverlay from "@/app/components/ui/loading-overlay";

function hasBackgroundPrefetchHeader(input, init) {
  try {
    const headers = new Headers(init?.headers || input?.headers || {});
    return headers.get("X-Background-Prefetch") === "1";
  } catch {
    return false;
  }
}

function shouldTrackApiRequest(input, init) {
  if (typeof window === "undefined") {
    return false;
  }
  if (hasBackgroundPrefetchHeader(input, init)) {
    return false;
  }

  const url = typeof input === "string" ? input : input?.url;
  if (!url) {
    return false;
  }

  try {
    const parsedUrl = new URL(url, window.location.origin);
    return parsedUrl.origin === window.location.origin && parsedUrl.pathname.startsWith("/api/");
  } catch {
    return false;
  }
}

function shouldTrackNavigationClick(event) {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.altKey ||
    event.ctrlKey ||
    event.shiftKey
  ) {
    return false;
  }

  const anchor = event.target.closest?.("a[href]");
  if (!anchor || anchor.target || anchor.hasAttribute("download")) {
    return false;
  }

  try {
    const nextUrl = new URL(anchor.href, window.location.origin);
    if (nextUrl.origin !== window.location.origin) {
      return false;
    }
    if (nextUrl.href === window.location.href) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

export default function ApiBusyOverlay() {
  const [pendingCount, setPendingCount] = useState(0);
  const [navigationPending, setNavigationPending] = useState(false);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);

    async function trackedFetch(...args) {
      const trackRequest = shouldTrackApiRequest(args[0], args[1]);
      if (!trackRequest) {
        return originalFetch(...args);
      }

      setPendingCount((current) => current + 1);
      try {
        return await originalFetch(...args);
      } finally {
        setPendingCount((current) => Math.max(0, current - 1));
      }
    }

    window.fetch = trackedFetch;
    return () => {
      if (window.fetch === trackedFetch) {
        window.fetch = originalFetch;
      }
    };
  }, []);

  useEffect(() => {
    function handleDocumentClick(event) {
      if (shouldTrackNavigationClick(event)) {
        setNavigationPending(true);
      }
    }

    document.addEventListener("click", handleDocumentClick, true);
    return () => document.removeEventListener("click", handleDocumentClick, true);
  }, []);

  useEffect(() => {
    if (!navigationPending) {
      return undefined;
    }

    const startHref = window.location.href;
    const intervalId = window.setInterval(() => {
      if (window.location.href !== startHref) {
        setNavigationPending(false);
      }
    }, 100);
    const timeoutId = window.setTimeout(() => setNavigationPending(false), 15000);

    return () => {
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
    };
  }, [navigationPending]);

  if (pendingCount === 0 && !navigationPending) {
    return null;
  }

  return <LoadingOverlay />;
}
