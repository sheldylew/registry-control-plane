"use client";

import Link from "next/link";
import { useId, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ClockIcon } from "@heroicons/react/24/outline";
import { ChevronDownIcon, ChevronUpDownIcon, ChevronUpIcon } from "@heroicons/react/20/solid";

import ActionMenu from "@/app/components/ui/action-menu";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import Dialog from "@/app/components/ui/dialog";
import EmptyState from "@/app/components/ui/empty-state";
import Pagination from "@/app/components/ui/pagination";
import { MobileCollapsiblePanel, PanelHeader } from "@/app/components/ui/panel";
import {
  MobileCardList,
  MobileDisclosureCard,
  MobileField,
  Table,
  TableBody,
  TableHead,
  TableShell,
} from "@/app/components/ui/table";
import RepoDeletePanel from "@/app/components/repo-delete-panel";
import { formatRelativeTime } from "@/app/lib/date-format";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

const SORT_OPTIONS = new Set(["created", "tag"]);
const DIRECTION_OPTIONS = new Set(["asc", "desc"]);

function normalizeSortState(sorting) {
  const sort = SORT_OPTIONS.has(sorting?.sort) ? sorting.sort : "created";
  const direction = DIRECTION_OPTIONS.has(sorting?.direction) ? sorting.direction : "desc";
  return { sort, direction };
}

function buildPageHref(repoPath, page, sorting) {
  const { sort, direction } = normalizeSortState(sorting);
  const basePath = `/repos/${encodeURIComponent(repoPath)}`;
  const params = new URLSearchParams();
  if (page > 1) {
    params.set("page", String(page));
  }
  if (sort !== "created" || direction !== "desc") {
    params.set("sort", sort);
    params.set("direction", direction);
  }
  const query = params.toString();
  return query ? `${basePath}?${query}` : basePath;
}

function buildSortHref(repoPath, sortKey, currentSorting) {
  const { sort, direction } = normalizeSortState(currentSorting);
  const nextDirection = sort === sortKey && direction === "asc" ? "desc" : "asc";
  return buildPageHref(repoPath, 1, { sort: sortKey, direction: nextDirection });
}

function buildTagDeleteRedirectPath(repoPath, pagination) {
  return buildBulkTagDeleteRedirectPath(repoPath, pagination, 1);
}

function buildBulkTagDeleteRedirectPath(repoPath, pagination, deleteCount) {
  const remainingTags = Math.max(Number(pagination?.total || 0) - deleteCount, 0);
  if (remainingTags === 0) {
    return "/repos";
  }

  const pageSize = Math.max(Number(pagination?.page_size || 1), 1);
  const currentPage = Math.max(Number(pagination?.page || 1), 1);
  const lastPageAfterDelete = Math.max(Math.ceil(remainingTags / pageSize), 1);
  return buildPageHref(repoPath, Math.min(currentPage, lastPageAfterDelete), pagination?.sorting);
}

function SortHeader({ repoPath, sorting, sortKey, align = "left", children }) {
  const { sort, direction } = normalizeSortState(sorting);
  const active = sort === sortKey;
  const nextDirection = active && direction === "asc" ? "desc" : "asc";
  const directionLabel = nextDirection === "asc" ? "ascending" : "descending";
  const SortIcon = active ? (direction === "asc" ? ChevronUpIcon : ChevronDownIcon) : ChevronUpDownIcon;

  return (
    <Link
      href={buildSortHref(repoPath, sortKey, sorting)}
      prefetch={false}
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
      aria-label={`Sort by ${children} ${directionLabel}`}
      className={`inline-flex items-center gap-1.5 rounded-md text-slate-300 transition hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-300/20 ${
        align === "center" ? "justify-center" : ""
      }`}
    >
      <span>{children}</span>
      <SortIcon
        className={`h-4 w-4 ${active ? "text-cyan-200" : "text-slate-500"}`}
        aria-hidden="true"
      />
    </Link>
  );
}

function buildSharedManifestWarning(item) {
  const count = Number(item.shared_manifest_tag_count || 0);
  if (count <= 1) {
    return null;
  }

  const tags = Array.isArray(item.shared_manifest_tags) ? item.shared_manifest_tags : [];
  const tagList = tags.length
    ? ` Active tags currently pointing at this manifest include ${tags.join(", ")}${count > tags.length ? ` and ${count - tags.length} more` : ""}.`
    : "";
  return `This manifest is shared by ${count} active tags. Deleting it can remove every tag that points at this digest.${tagList}`;
}

function formatBytes(size) {
  if (!size) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let unit = units[0];
  for (const candidate of units) {
    unit = candidate;
    if (value < 1024 || candidate === units[units.length - 1]) {
      break;
    }
    value /= 1024;
  }
  return `${value.toFixed(value >= 10 || unit === "B" ? 0 : 1)} ${unit}`;
}

function formatDigest(digest) {
  if (!digest) {
    return "Unavailable";
  }
  if (digest.length <= 20) {
    return digest;
  }
  return `${digest.slice(0, 15)}...${digest.slice(-8)}`;
}

function DigestTooltip({ digest }) {
  const tooltipId = useId();
  const [tooltipPosition, setTooltipPosition] = useState(null);
  const fullDigest = digest || "Unavailable";
  const isAvailable = Boolean(digest);

  function showTooltip(event) {
    if (!isAvailable) {
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    const gap = 10;
    const horizontalPadding = 16;
    const left = Math.min(
      Math.max(rect.left + rect.width / 2, horizontalPadding),
      window.innerWidth - horizontalPadding,
    );
    const placeBelow = rect.top < 96;
    setTooltipPosition({
      left,
      top: placeBelow ? rect.bottom + gap : rect.top - gap,
      placement: placeBelow ? "bottom" : "top",
    });
  }

  function hideTooltip() {
    setTooltipPosition(null);
  }

  return (
    <>
      <span
        className={`inline-flex max-w-full rounded-sm font-mono text-xs transition ${
          isAvailable
            ? "cursor-help text-slate-100 underline decoration-cyan-300/40 decoration-dotted underline-offset-4 hover:text-cyan-100 focus:text-cyan-100 focus:outline-none focus:ring-2 focus:ring-cyan-300/20"
            : "text-slate-500"
        }`}
        tabIndex={isAvailable ? 0 : undefined}
        aria-describedby={tooltipPosition ? tooltipId : undefined}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
      >
        <span className="truncate">{formatDigest(digest)}</span>
      </span>
      {tooltipPosition ? (
        <span
          id={tooltipId}
          role="tooltip"
          className="pointer-events-none fixed z-50 max-w-[min(44rem,calc(100vw-2rem))] rounded-lg border border-cyan-300/20 bg-slate-950/95 px-3 py-2 text-left text-xs leading-5 text-slate-100 shadow-xl shadow-slate-950/50 ring-1 ring-white/10 backdrop-blur"
          style={{
            left: `${tooltipPosition.left}px`,
            top: `${tooltipPosition.top}px`,
            transform: tooltipPosition.placement === "top" ? "translate(-50%, -100%)" : "translate(-50%, 0)",
          }}
        >
          <span className="block text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-cyan-200">Full digest</span>
          <span className="mt-1 block break-all font-mono text-slate-50">{fullDigest}</span>
        </span>
      ) : null}
    </>
  );
}

function formatPlatformLabel(value) {
  return value || "Unknown platform";
}

function checkboxClassName() {
  return "h-4 w-4 rounded border-white/20 bg-slate-950 text-cyan-300 accent-cyan-400 focus:ring-2 focus:ring-cyan-400/40";
}

export default function RepositoryTagsPanel({ payload, timeZone }) {
  const router = useRouter();
  const [selectedTags, setSelectedTags] = useState(() => new Set());
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false);
  const [bulkError, setBulkError] = useState("");
  const [bulkPending, setBulkPending] = useState(false);
  const tags = Array.isArray(payload.tags) ? payload.tags : [];
  const sorting = normalizeSortState(payload.sorting);
  const sortingForLinks = { ...sorting };
  const paginationForRedirects = { ...payload.pagination, sorting: sortingForLinks };
  const selectableTags = useMemo(() => tags.map((tag) => tag.tag), [tags]);
  const selectedTagList = selectableTags.filter((tag) => selectedTags.has(tag));
  const selectedItems = tags.filter((tag) => selectedTags.has(tag.tag));
  const selectedCount = selectedTagList.length;
  const allSelected = selectableTags.length > 0 && selectedCount === selectableTags.length;
  const selectedSharedManifestCount = selectedItems.filter((tag) => Number(tag.shared_manifest_tag_count || 0) > 1).length;

  function toggleTag(tagName) {
    setSelectedTags((current) => {
      const next = new Set(current);
      if (next.has(tagName)) {
        next.delete(tagName);
      } else {
        next.add(tagName);
      }
      return next;
    });
  }

  function toggleAllTags() {
    setSelectedTags((current) => {
      if (selectableTags.length > 0 && selectableTags.every((tag) => current.has(tag))) {
        return new Set();
      }
      return new Set(selectableTags);
    });
  }

  function openBulkDialog() {
    if (!selectedCount) {
      return;
    }
    setBulkError("");
    setBulkDialogOpen(true);
  }

  function closeBulkDialog() {
    if (bulkPending) {
      return;
    }
    setBulkDialogOpen(false);
    setBulkError("");
  }

  async function deleteSelectedTags() {
    setBulkPending(true);
    setBulkError("");

    try {
      const response = await fetch(`/api/repos/${encodeURIComponent(payload.repo)}/tags/delete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": readCookie("rcr_csrf"),
        },
        body: JSON.stringify({ tags: selectedTagList }),
      });
      const responsePayload = await response.json().catch(() => ({}));

      if (!response.ok) {
        setBulkError(responsePayload.detail || "Delete failed.");
        return;
      }

      const redirectPath = buildBulkTagDeleteRedirectPath(payload.repo, paginationForRedirects, selectedCount);
      setSelectedTags(new Set());
      setBulkDialogOpen(false);
      router.push(redirectPath);
      router.refresh();
    } catch {
      setBulkError("Delete failed.");
    } finally {
      setBulkPending(false);
    }
  }

  const headerAction = (
    <div className="flex items-center gap-2">
      {payload.can_delete_tag ? (
        <>
          {selectedCount ? (
            <Badge tone="slate">{selectedCount} selected</Badge>
          ) : null}
          <ActionMenu
            label="Tag actions"
            items={[
              {
                label: selectedCount ? `Delete ${selectedCount} selected` : "Delete selected",
                onSelect: openBulkDialog,
                disabled: selectedCount === 0,
                loading: bulkPending,
              },
            ]}
          />
        </>
      ) : null}
      <Badge tone="cyan">{payload.pagination.total} total</Badge>
    </div>
  );

  return (
    <MobileCollapsiblePanel
      className="p-4 sm:p-6"
      title="Tags"
      summaryMeta={`${payload.pagination.total} total`}
    >
      <PanelHeader title="Tags" action={headerAction} />
      {tags.length ? (
        <div className="mt-4">
          <div className="mb-3 grid grid-cols-2 gap-2 lg:hidden">
            <Button
              as={Link}
              href={buildSortHref(payload.repo, "created", sortingForLinks)}
              prefetch={false}
              variant={sorting.sort === "created" ? "primary" : "secondary"}
              size="sm"
              className="justify-center"
            >
              <ChevronUpDownIcon className="h-4 w-4" aria-hidden="true" />
              Created {sorting.sort === "created" ? (sorting.direction === "asc" ? "oldest" : "newest") : ""}
            </Button>
            <Button
              as={Link}
              href={buildSortHref(payload.repo, "tag", sortingForLinks)}
              prefetch={false}
              variant={sorting.sort === "tag" ? "primary" : "secondary"}
              size="sm"
              className="justify-center"
            >
              <ChevronUpDownIcon className="h-4 w-4" aria-hidden="true" />
              Tag {sorting.sort === "tag" ? (sorting.direction === "asc" ? "A-Z" : "Z-A") : ""}
            </Button>
          </div>
          <TableShell
            mobileCards={(
              <MobileCardList>
                {tags.map((tag) => (
                  <MobileDisclosureCard
                    key={tag.tag}
                    summary={(
                      <>
                        <Link
                          href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}`}
                          prefetch={false}
                          className="inline-flex max-w-full rounded-md border border-cyan-400/30 bg-cyan-400/10 px-2 py-1 text-sm font-semibold text-cyan-100 transition hover:border-cyan-300"
                        >
                          <span className="truncate">{tag.tag}</span>
                        </Link>
                        <p className="mt-2 text-xs text-slate-400">
                          Created {formatRelativeTime(tag.created_at, { timeZone })}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Badge tone="slate">{formatBytes(tag.total_size)}</Badge>
                          {tag.history_count === null ? null : <Badge tone="cyan">{tag.history_count} history</Badge>}
                        </div>
                      </>
                    )}
                  >
                    {payload.can_delete_tag ? (
                      <label className="flex items-center gap-3 rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200">
                        <input
                          type="checkbox"
                          checked={selectedTags.has(tag.tag)}
                          onChange={() => toggleTag(tag.tag)}
                          className={checkboxClassName()}
                        />
                        <span>Select tag</span>
                      </label>
                    ) : null}

                    <dl className="mt-4 grid gap-4">
                      <MobileField label="Content digest">
                        <DigestTooltip digest={tag.digest} />
                      </MobileField>
                      <MobileField label="Platforms">
                        <div className="flex flex-wrap gap-2">
                          {tag.architectures.length ? (
                            tag.architectures.map((arch) => (
                              <span
                                key={arch}
                                className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200"
                              >
                                {formatPlatformLabel(arch)}
                              </span>
                            ))
                          ) : (
                            <span className="text-slate-500">Unknown platform</span>
                          )}
                        </div>
                      </MobileField>
                    </dl>

                    <div className="mt-4 grid gap-2 sm:grid-cols-2">
                      <Button
                        as={Link}
                        href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}/history`}
                        prefetch={false}
                        variant="secondary"
                        size="sm"
                        className="justify-center"
                      >
                        History{tag.history_count === null ? "" : ` (${tag.history_count})`}
                      </Button>
                      {payload.can_delete_tag ? (
                        <RepoDeletePanel
                          compact
                          title="Delete tag"
                          description="This resolves the tag to its manifest digest and deletes that manifest from the registry. Disk space is not reclaimed until registry garbage collection runs."
                          warning={buildSharedManifestWarning(tag)}
                          confirmationValue={`${payload.repo}:${tag.tag}`}
                          requireConfirmation={false}
                          endpoint={`/api/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}/delete`}
                          redirectPath={buildTagDeleteRedirectPath(payload.repo, paginationForRedirects)}
                          buttonLabel="Delete"
                          successLabel="Deleting..."
                        />
                      ) : null}
                    </div>
                  </MobileDisclosureCard>
                ))}
              </MobileCardList>
            )}
          >
            <Table>
              <TableHead>
                <tr>
                  {payload.can_delete_tag ? (
                    <th className="w-12 px-4 py-4 font-medium">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleAllTags}
                        aria-label="Select all tags"
                        className={checkboxClassName()}
                      />
                    </th>
                  ) : null}
                  <th className="px-4 py-4 font-medium">
                    <SortHeader repoPath={payload.repo} sorting={sortingForLinks} sortKey="created">
                      Created
                    </SortHeader>
                  </th>
                  <th className="px-4 py-4 font-medium">Size</th>
                  <th className="px-4 py-4 font-medium">Content Digest</th>
                  <th className="px-4 py-4 text-center font-medium">
                    <SortHeader repoPath={payload.repo} sorting={sortingForLinks} sortKey="tag" align="center">
                      Tag
                    </SortHeader>
                  </th>
                  <th className="px-4 py-4 font-medium">Arch</th>
                  <th className="px-4 py-4 font-medium">History</th>
                  {payload.can_delete_tag ? <th className="px-4 py-4 text-right font-medium">Delete</th> : null}
                </tr>
              </TableHead>
              <TableBody>
                {tags.map((tag) => (
                  <tr key={tag.tag}>
                    {payload.can_delete_tag ? (
                      <td className="px-4 py-4 align-top">
                        <input
                          type="checkbox"
                          checked={selectedTags.has(tag.tag)}
                          onChange={() => toggleTag(tag.tag)}
                          aria-label={`Select ${tag.tag}`}
                          className={checkboxClassName()}
                        />
                      </td>
                    ) : null}
                    <td className="px-4 py-4 align-top text-slate-300">
                      {formatRelativeTime(tag.created_at, { timeZone })}
                    </td>
                    <td className="px-4 py-4 align-top text-slate-300">{formatBytes(tag.total_size)}</td>
                    <td className="px-4 py-4 align-top">
                      <DigestTooltip digest={tag.digest} />
                    </td>
                    <td className="px-4 py-4 align-top text-center">
                      <Link
                        href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}`}
                        prefetch={false}
                        className="inline-flex rounded-md border border-cyan-400/30 bg-cyan-400/10 px-2 py-1 font-medium text-cyan-200 transition hover:border-cyan-300 hover:text-cyan-100"
                      >
                        {tag.tag}
                      </Link>
                    </td>
                    <td className="px-4 py-4 align-top">
                      <div className="flex flex-wrap gap-2">
                        {tag.architectures.length ? (
                          tag.architectures.map((arch) => (
                            <span
                              key={arch}
                              className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200"
                            >
                              {formatPlatformLabel(arch)}
                            </span>
                          ))
                        ) : (
                          <span className="text-slate-500">Unknown platform</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-4 align-top text-slate-300">
                      <Link
                        href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}/history`}
                        prefetch={false}
                        className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-white/10 bg-white/5 text-slate-200 transition hover:border-cyan-400/40 hover:text-white"
                        title={tag.history_count === null ? "View history" : `View ${tag.history_count} history entries`}
                        aria-label={tag.history_count === null ? "View history" : `View ${tag.history_count} history entries`}
                      >
                        <ClockIcon className="h-5 w-5" aria-hidden="true" />
                      </Link>
                    </td>
                    {payload.can_delete_tag ? (
                      <td className="px-4 py-4 align-top text-right">
                        <RepoDeletePanel
                          compact
                          title="Delete tag"
                          description="This resolves the tag to its manifest digest and deletes that manifest from the registry. Disk space is not reclaimed until registry garbage collection runs."
                          warning={buildSharedManifestWarning(tag)}
                          confirmationValue={`${payload.repo}:${tag.tag}`}
                          requireConfirmation={false}
                          endpoint={`/api/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}/delete`}
                          redirectPath={buildTagDeleteRedirectPath(payload.repo, paginationForRedirects)}
                          buttonLabel="Delete"
                          successLabel="Deleting..."
                        />
                      </td>
                    ) : null}
                  </tr>
                ))}
              </TableBody>
            </Table>
          </TableShell>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <EmptyState
            title="No tags returned"
            description="No tags were returned by the registry for this repository."
          />
          {payload.can_prune_repository ? (
            <RepoDeletePanel
              title="Delete empty repository"
              description="This removes the empty repository directory from registry storage. Use it only after all tags and manifests are gone."
              confirmationLabel="Type the repository name to confirm"
              confirmationValue={payload.repo}
              endpoint={`/api/repos/${encodeURIComponent(payload.repo)}/delete`}
              buttonLabel="Delete empty repository"
              successLabel="Deleting..."
            />
          ) : null}
        </div>
      )}
      <Pagination
        page={payload.pagination.page}
        pageSize={payload.pagination.page_size}
        total={payload.pagination.total}
        label="tags"
        hrefForPage={(page) => buildPageHref(payload.repo, page, sortingForLinks)}
      />

      <Dialog
        open={bulkDialogOpen}
        onClose={closeBulkDialog}
        eyebrow="Confirm delete"
        title={`Delete ${selectedCount} selected tag${selectedCount === 1 ? "" : "s"}`}
      >
        <p className="text-sm leading-7 text-slate-300">
          This resolves each selected tag to its manifest digest and deletes those manifests from the registry. Disk space is not reclaimed until registry garbage collection runs.
        </p>
        {selectedSharedManifestCount ? (
          <div className="mt-4 rounded-lg border border-amber-300/30 bg-amber-300/10 p-4 text-sm leading-7 text-amber-100">
            {selectedSharedManifestCount} selected tag{selectedSharedManifestCount === 1 ? "" : "s"} point to shared manifests. Deleting them can remove every tag that points at those digests.
          </div>
        ) : null}
        <div className="mt-4 max-h-48 overflow-auto rounded-lg border border-white/10 bg-slate-950/70 p-3">
          <ul className="space-y-2">
            {selectedTagList.map((tagName) => (
              <li key={tagName} className="break-all font-mono text-xs text-slate-200">
                {tagName}
              </li>
            ))}
          </ul>
        </div>
        {bulkError ? <p className="mt-3 text-sm text-rose-200">{bulkError}</p> : null}
        <div className="mt-5 grid gap-3 sm:flex sm:items-center sm:justify-end">
          <Button
            type="button"
            onClick={closeBulkDialog}
            disabled={bulkPending}
            variant="secondary"
            className="w-full sm:w-auto"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={deleteSelectedTags}
            disabled={bulkPending || selectedCount === 0}
            loading={bulkPending}
            variant="danger"
            className="w-full sm:w-auto"
          >
            {bulkPending ? "Deleting..." : "Delete selected"}
          </Button>
        </div>
      </Dialog>
    </MobileCollapsiblePanel>
  );
}
