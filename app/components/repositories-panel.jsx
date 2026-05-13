"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";

import { ChevronLeftIcon, ChevronRightIcon } from "@heroicons/react/20/solid";

import Badge from "@/app/components/ui/badge";
import EmptyState from "@/app/components/ui/empty-state";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { readApiErrorDetail } from "@/app/lib/user-form";

const repositoryPageCache = new Map();

function buildApiPath(page) {
  return `/api/repos?page=${String(page)}`;
}

function buildPageHref(page) {
  if (page <= 1) {
    return "/repos";
  }
  const params = new URLSearchParams();
  params.set("page", String(page));
  return `/repos?${params.toString()}`;
}

function pageFromLocation() {
  const params = new URLSearchParams(window.location.search);
  return Math.max(Number(params.get("page") || "1") || 1, 1);
}

function buildPageItems(page, totalPages) {
  const pages = new Set([1, totalPages, page - 1, page, page + 1]);
  if (page <= 3) {
    pages.add(2);
    pages.add(3);
  }
  if (page >= totalPages - 2) {
    pages.add(totalPages - 1);
    pages.add(totalPages - 2);
  }

  const ordered = [...pages].filter((value) => value >= 1 && value <= totalPages).sort((a, b) => a - b);
  const items = [];
  for (let index = 0; index < ordered.length; index += 1) {
    const value = ordered[index];
    const previous = ordered[index - 1];
    if (previous && value - previous > 1) {
      items.push("gap");
    }
    items.push(value);
  }
  return items;
}

function isPlainNavigation(event) {
  return !(
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.altKey ||
    event.ctrlKey ||
    event.shiftKey
  );
}

async function fetchRepositoryPage(page, { background = false, signal } = {}) {
  const response = await fetch(buildApiPath(page), {
    headers: {
      Accept: "application/json",
      ...(background ? { "X-Background-Prefetch": "1" } : {}),
    },
    signal,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(readApiErrorDetail(payload, "Failed to load repositories."));
  }
  repositoryPageCache.set(page, payload);
  return payload;
}

function RepositoryList({ repos }) {
  if (!repos.length) {
    return (
      <div className="mt-6">
        <EmptyState
          title="No visible repositories"
          description="No repositories are visible for this account yet."
        />
      </div>
    );
  }

  return (
    <ul className="mt-4 divide-y divide-white/10 overflow-hidden rounded-lg border border-white/10 bg-slate-950/50">
      {repos.map((repo) => (
        <li key={repo.name}>
          <Link
            href={`/repos/${encodeURIComponent(repo.name)}`}
            prefetch={false}
            className="block px-5 py-4 transition hover:bg-white/5"
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="break-words text-base font-semibold text-white">{repo.name}</p>
                <p className="mt-1 text-sm text-slate-400">Open tags and manifest details</p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <Badge tone={repo.visibility === "public" ? "emerald" : "slate"} dot>
                  {repo.visibility === "public" ? "Public" : "Private"}
                </Badge>
                <span className="text-sm text-cyan-200">Open</span>
              </div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RepositoryPagination({ pagination, onNavigate, onPrefetch }) {
  const totalPages = Math.max(Math.ceil(pagination.total / pagination.page_size), 1);
  const currentPage = Math.min(Math.max(pagination.page, 1), totalPages);
  const start = pagination.total === 0 ? 0 : (currentPage - 1) * pagination.page_size + 1;
  const end = pagination.total === 0 ? 0 : Math.min(currentPage * pagination.page_size, pagination.total);
  const items = buildPageItems(currentPage, totalPages);

  function linkProps(targetPage) {
    return {
      href: buildPageHref(targetPage),
      prefetch: false,
      onClick: (event) => onNavigate(event, targetPage),
      onMouseEnter: () => onPrefetch(targetPage),
      onFocus: () => onPrefetch(targetPage),
    };
  }

  return (
    <div className="mt-6 border-t border-white/10 px-4 py-3 sm:flex sm:items-center sm:justify-between sm:px-6">
      <div className="space-y-3 sm:hidden">
        <p className="text-center text-xs text-slate-400">
          Showing <span className="font-medium text-white">{start}</span> to{" "}
          <span className="font-medium text-white">{end}</span> of{" "}
          <span className="font-medium text-white">{pagination.total}</span> repositories
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Link
            {...linkProps(Math.max(currentPage - 1, 1))}
            aria-disabled={currentPage <= 1}
            className={`relative inline-flex items-center justify-center rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium ${
              currentPage <= 1 ? "pointer-events-none text-slate-500 opacity-50" : "text-slate-200 hover:bg-white/10"
            }`}
          >
            Previous
          </Link>
          <Link
            {...linkProps(Math.min(currentPage + 1, totalPages))}
            aria-disabled={currentPage >= totalPages}
            className={`relative inline-flex items-center justify-center rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium ${
              currentPage >= totalPages ? "pointer-events-none text-slate-500 opacity-50" : "text-slate-200 hover:bg-white/10"
            }`}
          >
            Next
          </Link>
        </div>
      </div>
      <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
        <p className="text-sm text-slate-300">
          Showing <span className="font-medium text-white">{start}</span> to{" "}
          <span className="font-medium text-white">{end}</span> of{" "}
          <span className="font-medium text-white">{pagination.total}</span> repositories
        </p>
        <nav aria-label="Pagination" className="isolate inline-flex -space-x-px rounded-md">
          <Link
            {...linkProps(Math.max(currentPage - 1, 1))}
            aria-disabled={currentPage <= 1}
            className={`relative inline-flex items-center rounded-l-md px-2 py-2 ring-1 ring-inset ring-white/10 ${
              currentPage <= 1 ? "pointer-events-none text-slate-600 opacity-50" : "text-slate-400 hover:bg-white/5"
            }`}
          >
            <span className="sr-only">Previous</span>
            <ChevronLeftIcon className="h-5 w-5" />
          </Link>
          {items.map((item, index) =>
            item === "gap" ? (
              <span
                key={`gap-${index}`}
                className="relative inline-flex items-center px-4 py-2 text-sm font-semibold text-slate-500 ring-1 ring-inset ring-white/10"
              >
                ...
              </span>
            ) : item === currentPage ? (
              <span
                key={item}
                aria-current="page"
                className="relative z-10 inline-flex items-center bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950"
              >
                {item}
              </span>
            ) : (
              <Link
                key={item}
                {...linkProps(item)}
                className="relative inline-flex items-center px-4 py-2 text-sm font-semibold text-slate-200 ring-1 ring-inset ring-white/10 hover:bg-white/5"
              >
                {item}
              </Link>
            ),
          )}
          <Link
            {...linkProps(Math.min(currentPage + 1, totalPages))}
            aria-disabled={currentPage >= totalPages}
            className={`relative inline-flex items-center rounded-r-md px-2 py-2 ring-1 ring-inset ring-white/10 ${
              currentPage >= totalPages ? "pointer-events-none text-slate-600 opacity-50" : "text-slate-400 hover:bg-white/5"
            }`}
          >
            <span className="sr-only">Next</span>
            <ChevronRightIcon className="h-5 w-5" />
          </Link>
        </nav>
      </div>
    </div>
  );
}

export default function RepositoriesPanel({ initialPayload }) {
  const initialPage = initialPayload.pagination.page;
  const [payload, setPayload] = useState(initialPayload);
  const [pendingPage, setPendingPage] = useState(null);
  const [error, setError] = useState("");
  const [, startTransition] = useTransition();
  const requestRef = useRef({ id: 0, controller: null });

  useEffect(() => {
    repositoryPageCache.set(initialPage, initialPayload);
    setPayload(initialPayload);
  }, [initialPage, initialPayload]);

  useEffect(() => {
    function handlePopState() {
      loadPage(pageFromLocation(), { updateHistory: false });
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  });

  async function loadPage(nextPage, { updateHistory = true } = {}) {
    const safePage = Math.max(Number(nextPage) || 1, 1);
    const cachedPayload = repositoryPageCache.get(safePage);
    setError("");

    if (cachedPayload) {
      startTransition(() => setPayload(cachedPayload));
    }

    if (updateHistory) {
      window.history.pushState(null, "", buildPageHref(safePage));
    }

    requestRef.current.controller?.abort();
    const controller = new AbortController();
    const requestId = requestRef.current.id + 1;
    requestRef.current = { id: requestId, controller };
    setPendingPage(safePage);

    try {
      const nextPayload = await fetchRepositoryPage(safePage, { signal: controller.signal });
      if (requestRef.current.id !== requestId) {
        return;
      }
      startTransition(() => setPayload(nextPayload));
    } catch (fetchError) {
      if (fetchError.name === "AbortError") {
        return;
      }
      setError(fetchError.message || "Failed to load repositories.");
    } finally {
      if (requestRef.current.id === requestId) {
        setPendingPage(null);
      }
    }
  }

  function handleNavigate(event, nextPage) {
    if (!isPlainNavigation(event)) {
      return;
    }
    event.preventDefault();
    if (nextPage === payload.pagination.page && pendingPage === null) {
      return;
    }
    loadPage(nextPage);
  }

  function prefetchPage(nextPage) {
    if (repositoryPageCache.has(nextPage) || nextPage === payload.pagination.page) {
      return;
    }
    fetchRepositoryPage(nextPage, { background: true }).catch(() => {});
  }

  const isRefreshing = pendingPage !== null;

  return (
    <Panel className="p-4 sm:p-6" aria-busy={isRefreshing || undefined}>
      <PanelHeader
        title="Visible repositories"
        action={<Badge tone="cyan">{payload.pagination.total} visible</Badge>}
      />
      <div className="relative">
        {isRefreshing ? (
          <div className="absolute inset-x-0 top-0 z-10 h-px overflow-hidden bg-white/10">
            <div className="h-full w-1/3 animate-pulse bg-cyan-300" />
            <span className="sr-only">Refreshing repositories</span>
          </div>
        ) : null}
        <div className={isRefreshing ? "opacity-75 transition-opacity" : "transition-opacity"}>
          <RepositoryList repos={payload.repos} />
        </div>
      </div>
      {error ? <p className="mt-4 text-sm text-rose-200">{error}</p> : null}
      <RepositoryPagination
        pagination={payload.pagination}
        onNavigate={handleNavigate}
        onPrefetch={prefetchPage}
      />
    </Panel>
  );
}
