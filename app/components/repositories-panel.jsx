"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";

import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpDownIcon,
  ChevronUpIcon,
} from "@heroicons/react/20/solid";

import Badge from "@/app/components/ui/badge";
import EmptyState from "@/app/components/ui/empty-state";
import { MobileCard, MobileCardList, MobileField, Table, TableBody, TableHead, TableShell } from "@/app/components/ui/table";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { formatDateTime, formatRelativeTime } from "@/app/lib/date-format";
import { readApiErrorDetail } from "@/app/lib/user-form";

const SORT_OPTIONS = new Set(["updated", "name"]);
const DIRECTION_OPTIONS = new Set(["asc", "desc"]);

function normalizeSortState(sorting) {
  const sort = SORT_OPTIONS.has(sorting?.sort) ? sorting.sort : "updated";
  const direction = DIRECTION_OPTIONS.has(sorting?.direction) ? sorting.direction : "desc";
  return { sort, direction };
}

function buildApiPath(page, sorting) {
  const { sort, direction } = normalizeSortState(sorting);
  const params = new URLSearchParams();
  params.set("page", String(page));
  if (sort !== "updated" || direction !== "desc") {
    params.set("sort", sort);
    params.set("direction", direction);
  }
  return `/api/repos?${params.toString()}`;
}

function buildPageHref(page, sorting) {
  if (page <= 1) {
    const params = new URLSearchParams();
    const { sort, direction } = normalizeSortState(sorting);
    if (sort !== "updated" || direction !== "desc") {
      params.set("sort", sort);
      params.set("direction", direction);
    }
    const query = params.toString();
    return query ? `/repos?${query}` : "/repos";
  }
  const params = new URLSearchParams();
  params.set("page", String(page));
  const { sort, direction } = normalizeSortState(sorting);
  if (sort !== "updated" || direction !== "desc") {
    params.set("sort", sort);
    params.set("direction", direction);
  }
  return `/repos?${params.toString()}`;
}

function readStateFromLocation() {
  const params = new URLSearchParams(window.location.search);
  return {
    page: Math.max(Number(params.get("page") || "1") || 1, 1),
    sorting: normalizeSortState({
      sort: params.get("sort"),
      direction: params.get("direction"),
    }),
  };
}

function buildCacheKey(page, sorting) {
  const { sort, direction } = normalizeSortState(sorting);
  return `${page}:${sort}:${direction}`;
}

function buildSortHref(sortKey, currentSorting) {
  const { sort, direction } = normalizeSortState(currentSorting);
  const nextDirection = sort === sortKey && direction === "asc" ? "desc" : "asc";
  return buildPageHref(1, { sort: sortKey, direction: nextDirection });
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

async function fetchRepositoryPage(page, sorting, cache, { background = false, signal } = {}) {
  const response = await fetch(buildApiPath(page, sorting), {
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
  cache.set(buildCacheKey(page, sorting), payload);
  return payload;
}

function SortHeader({ sorting, sortKey, align = "left", children }) {
  const { sort, direction } = normalizeSortState(sorting);
  const active = sort === sortKey;
  const nextDirection = active && direction === "asc" ? "desc" : "asc";
  const directionLabel = nextDirection === "asc" ? "ascending" : "descending";
  const SortIcon = active ? (direction === "asc" ? ChevronUpIcon : ChevronDownIcon) : ChevronUpDownIcon;

  return (
    <Link
      href={buildSortHref(sortKey, sorting)}
      prefetch={false}
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
      aria-label={`Sort by ${children} ${directionLabel}`}
      className={`inline-flex items-center gap-1.5 rounded-md text-slate-300 transition hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-300/20 ${
        align === "center" ? "justify-center" : ""
      }`}
    >
      <span>{children}</span>
      <SortIcon className={`h-4 w-4 ${active ? "text-cyan-200" : "text-slate-500"}`} aria-hidden="true" />
    </Link>
  );
}

function ModifiedDate({ value, timeZone }) {
  return (
    <div className="space-y-1">
      <div className="text-sm font-medium text-white">{formatRelativeTime(value, { timeZone })}</div>
      <div className="text-xs text-slate-500">{formatDateTime(value, { timeZone })}</div>
    </div>
  );
}

function RepositoryTable({ repos, sorting, timeZone }) {
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
    <TableShell
      mobileCards={
        <MobileCardList>
          {repos.map((repo) => (
            <MobileCard key={repo.name}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <Link
                    href={`/repos/${encodeURIComponent(repo.name)}`}
                    prefetch={false}
                    className="break-words text-base font-semibold text-white transition hover:text-cyan-200"
                  >
                    {repo.name}
                  </Link>
                  <p className="mt-1 text-sm text-slate-400">Open tags and manifest details</p>
                </div>
                <Badge tone={repo.visibility === "public" ? "emerald" : "slate"} dot>
                  {repo.visibility === "public" ? "Public" : "Private"}
                </Badge>
              </div>
              <dl className="mt-4 grid grid-cols-1 gap-4 border-t border-white/10 pt-4">
                <MobileField label="Modified">
                  <ModifiedDate value={repo.updated_at} timeZone={timeZone} />
                </MobileField>
              </dl>
              <div className="mt-4 flex items-center justify-between gap-3">
                <Badge tone={repo.visibility === "public" ? "emerald" : "slate"} dot>
                  {repo.visibility === "public" ? "Public" : "Private"}
                </Badge>
                <Link
                  href={`/repos/${encodeURIComponent(repo.name)}`}
                  prefetch={false}
                  className="inline-flex items-center rounded-md border border-cyan-300/20 bg-cyan-400/10 px-3 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-400/20"
                >
                  Open
                </Link>
              </div>
            </MobileCard>
          ))}
        </MobileCardList>
      }
    >
      <Table>
        <TableHead>
          <tr>
            <th scope="col" className="px-5 py-3 font-semibold">
              <SortHeader sorting={sorting} sortKey="name">Repository</SortHeader>
            </th>
            <th scope="col" className="px-5 py-3 font-semibold">
              <SortHeader sorting={sorting} sortKey="updated">Modified</SortHeader>
            </th>
            <th scope="col" className="px-5 py-3 text-right font-semibold">
              Open
            </th>
          </tr>
        </TableHead>
        <TableBody>
          {repos.map((repo) => (
            <tr key={repo.name} className="bg-slate-950/50 transition hover:bg-white/5">
              <td className="px-5 py-4 align-top">
                <Link
                  href={`/repos/${encodeURIComponent(repo.name)}`}
                  prefetch={false}
                  className="break-words text-sm font-semibold text-white transition hover:text-cyan-200"
                >
                  {repo.name}
                </Link>
                <p className="mt-1 text-sm text-slate-400">Open tags and manifest details</p>
              </td>
              <td className="px-5 py-4 align-top">
                <ModifiedDate value={repo.updated_at} timeZone={timeZone} />
              </td>
              <td className="px-5 py-4 text-right align-top">
                <div className="flex items-center justify-end gap-3">
                  <Badge tone={repo.visibility === "public" ? "emerald" : "slate"} dot>
                    {repo.visibility === "public" ? "Public" : "Private"}
                  </Badge>
                  <Link
                    href={`/repos/${encodeURIComponent(repo.name)}`}
                    prefetch={false}
                    className="text-sm font-semibold text-cyan-200 transition hover:text-cyan-100"
                  >
                    Open
                  </Link>
                </div>
              </td>
            </tr>
          ))}
        </TableBody>
      </Table>
    </TableShell>
  );
}

function RepositoryPagination({ pagination, sorting, onNavigate, onPrefetch }) {
  const totalPages = Math.max(Math.ceil(pagination.total / pagination.page_size), 1);
  const currentPage = Math.min(Math.max(pagination.page, 1), totalPages);
  const start = pagination.total === 0 ? 0 : (currentPage - 1) * pagination.page_size + 1;
  const end = pagination.total === 0 ? 0 : Math.min(currentPage * pagination.page_size, pagination.total);
  const items = buildPageItems(currentPage, totalPages);

  function linkProps(targetPage) {
    return {
      href: buildPageHref(targetPage, sorting),
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

export default function RepositoriesPanel({ initialPayload, timeZone }) {
  const initialPage = initialPayload.pagination.page;
  const initialSorting = normalizeSortState(initialPayload.sorting);
  const [payload, setPayload] = useState(initialPayload);
  const [pendingKey, setPendingKey] = useState(null);
  const [error, setError] = useState("");
  const [, startTransition] = useTransition();
  const requestRef = useRef({ id: 0, controller: null });
  const cacheRef = useRef(new Map());
  const userIdRef = useRef(initialPayload.user?.id ?? null);

  useEffect(() => {
    requestRef.current.controller?.abort();
    requestRef.current = { id: requestRef.current.id + 1, controller: null };
    setPendingKey(null);
    if (userIdRef.current !== (initialPayload.user?.id ?? null)) {
      cacheRef.current.clear();
      userIdRef.current = initialPayload.user?.id ?? null;
    }
    cacheRef.current.set(buildCacheKey(initialPage, initialSorting), initialPayload);
    setPayload(initialPayload);
  }, [initialPage, initialPayload, initialSorting.direction, initialSorting.sort]);

  useEffect(() => {
    function handlePopState() {
      const nextState = readStateFromLocation();
      loadPage(nextState.page, nextState.sorting, { updateHistory: false });
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  });

  async function loadPage(nextPage, nextSorting, { updateHistory = true } = {}) {
    const safePage = Math.max(Number(nextPage) || 1, 1);
    const safeSorting = normalizeSortState(nextSorting);
    const cacheKey = buildCacheKey(safePage, safeSorting);
    const cachedPayload = cacheRef.current.get(cacheKey);
    setError("");

    if (cachedPayload) {
      startTransition(() => setPayload(cachedPayload));
    }

    if (updateHistory) {
      window.history.pushState(null, "", buildPageHref(safePage, safeSorting));
    }

    requestRef.current.controller?.abort();
    const controller = new AbortController();
    const requestId = requestRef.current.id + 1;
    requestRef.current = { id: requestId, controller };
    setPendingKey(cacheKey);

    try {
      const nextPayload = await fetchRepositoryPage(safePage, safeSorting, cacheRef.current, { signal: controller.signal });
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
        setPendingKey(null);
      }
    }
  }

  const sorting = normalizeSortState(payload.sorting);

  function handleNavigate(event, nextPage) {
    if (!isPlainNavigation(event)) {
      return;
    }
    event.preventDefault();
    const cacheKey = buildCacheKey(nextPage, sorting);
    if (nextPage === payload.pagination.page && pendingKey == null && cacheKey === buildCacheKey(payload.pagination.page, sorting)) {
      return;
    }
    loadPage(nextPage, sorting);
  }

  function prefetchPage(nextPage) {
    const cacheKey = buildCacheKey(nextPage, sorting);
    if (cacheRef.current.has(cacheKey) || nextPage === payload.pagination.page) {
      return;
    }
    fetchRepositoryPage(nextPage, sorting, cacheRef.current, { background: true }).catch(() => {});
  }

  const isRefreshing = pendingKey !== null;

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
          <RepositoryTable repos={payload.repos} sorting={sorting} timeZone={timeZone} />
        </div>
      </div>
      {error ? <p className="mt-4 text-sm text-rose-200">{error}</p> : null}
      <RepositoryPagination
        pagination={payload.pagination}
        sorting={sorting}
        onNavigate={handleNavigate}
        onPrefetch={prefetchPage}
      />
    </Panel>
  );
}
