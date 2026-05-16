import Link from "next/link";

import InboxRetryButton from "@/app/components/inbox-retry-button";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import Disclosure from "@/app/components/ui/disclosure";
import EmptyState from "@/app/components/ui/empty-state";
import { MobileCollapsiblePanel, Panel, PanelHeader } from "@/app/components/ui/panel";
import Pagination from "@/app/components/ui/pagination";
import { MobileCardList, MobileDisclosureCard, MobileField, Table, TableBody, TableHead, TableShell } from "@/app/components/ui/table";
import { formatDateTime } from "@/app/lib/date-format";
import { apiFetch } from "@/app/lib/server-api";
import { getUiTimezone } from "@/app/lib/ui-settings";

const statusFilters = [
  { value: "failed", label: "Failed" },
  { value: "pending", label: "Pending" },
  { value: "processing", label: "Processing" },
  { value: "processed", label: "Processed" },
  { value: "reconciled", label: "Reconciled" },
  { value: "all", label: "All" },
];

function statusTone(status) {
  if (status === "failed") {
    return "rose";
  }
  if (status === "pending" || status === "processing") {
    return "amber";
  }
  if (status === "processed" || status === "reconciled") {
    return "emerald";
  }
  return "slate";
}

function buildApiPath(status, page) {
  const params = new URLSearchParams();
  if (status && status !== "all") {
    params.set("status_filter", status);
  }
  params.set("page", String(page));
  return `/api/admin/maintenance/inbox?${params.toString()}`;
}

function buildPageHref(status, page) {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  if (page > 1) {
    params.set("page", String(page));
  }
  const query = params.toString();
  return query ? `/admin/maintenance/inbox?${query}` : "/admin/maintenance/inbox";
}

function countAllStatuses(statusCounts) {
  return Object.values(statusCounts).reduce((sum, count) => sum + count, 0);
}

function compactReference(entry) {
  if (entry.tag) {
    return entry.tag;
  }
  if (entry.digest) {
    return entry.digest;
  }
  return "No tag or digest";
}

function EntryDetails({ entry, timeZone }) {
  return (
    <div className="space-y-4">
      {entry.error ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-rose-200">Error</p>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-rose-300/20 bg-rose-950/20 px-4 py-3 text-xs leading-5 text-rose-50">
            {entry.error}
          </pre>
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <MobileField label="Dedupe key">
          <span className="break-all font-mono">{entry.dedupe_key}</span>
        </MobileField>
        <MobileField label="Media type">
          <span className="break-all">{entry.media_type || "Not recorded"}</span>
        </MobileField>
        <MobileField label="Received">
          {formatDateTime(entry.received_at, { timeZone, fallback: "Unknown" })}
        </MobileField>
        <MobileField label="Processed">
          {formatDateTime(entry.processed_at, { timeZone, fallback: "Not processed" })}
        </MobileField>
      </div>
      <Disclosure titleClosed="View raw payload" titleOpen="Hide raw payload">
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words border-t border-white/10 px-4 py-4 text-xs leading-5 text-slate-200">
          {JSON.stringify(entry.raw_payload || {}, null, 2)}
        </pre>
      </Disclosure>
      {entry.status === "failed" ? <InboxRetryButton entryId={entry.id} /> : null}
    </div>
  );
}

export default async function RegistryEventInboxPage({ searchParams }) {
  const [resolvedSearchParams, timeZone] = await Promise.all([
    searchParams,
    getUiTimezone(),
  ]);
  const requestedStatus = resolvedSearchParams?.status ?? "failed";
  const validStatus = statusFilters.some((filter) => filter.value === requestedStatus) ? requestedStatus : "failed";
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(buildApiPath(validStatus, page));
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load registry event inbox.");
  }

  const totalEntryCount = countAllStatuses(payload.status_counts);
  const totalForFilter = validStatus === "all" ? totalEntryCount : payload.status_counts[validStatus] || 0;

  return (
    <div className="space-y-6">
      <Panel as="section" className="p-4 sm:p-6">
        <PanelHeader
          eyebrow="Registry event inbox"
          title="Notification processing"
          description="Review registry push and delete notifications that update the database-backed repository state."
          action={(
            <Button as={Link} href="/admin/maintenance" prefetch={false} variant="secondary" className="w-full sm:w-auto">
              Back to maintenance
            </Button>
          )}
        />
        <div className="mt-5 flex flex-wrap gap-2">
          {statusFilters.map((filter) => (
            <Button
              key={filter.label}
              as={Link}
              href={buildPageHref(filter.value, 1)}
              prefetch={false}
              variant={filter.value === validStatus ? "soft" : "secondary"}
              size="sm"
              className="min-w-24"
            >
              {filter.label}
              <Badge tone={statusTone(filter.value)}>
                {filter.value === "all" ? totalEntryCount : payload.status_counts[filter.value] || 0}
              </Badge>
            </Button>
          ))}
        </div>
      </Panel>

      <MobileCollapsiblePanel
        as="section"
        className="p-4 sm:p-6"
        eyebrow="Inbox entries"
        title="Matching notifications"
        summaryMeta={`${totalForFilter} entries`}
        openLabel="Open inbox entries"
        hideLabel="Hide inbox entries"
      >
        {payload.entries.length ? (
          <TableShell
            mobileCards={(
              <MobileCardList>
                {payload.entries.map((entry) => (
                  <MobileDisclosureCard
                    key={entry.id}
                    summary={(
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-white">#{entry.id} {entry.action}</p>
                          <Badge tone={statusTone(entry.status)}>{entry.status}</Badge>
                        </div>
                        <p className="mt-1 break-all text-sm leading-6 text-slate-300">{entry.repository_name}</p>
                        <p className="mt-1 break-all text-xs leading-5 text-slate-400">{compactReference(entry)}</p>
                      </div>
                    )}
                  >
                    <dl className="grid gap-3">
                      <MobileField label="Attempts">{entry.attempts}</MobileField>
                      <MobileField label="Received">{formatDateTime(entry.received_at, { timeZone, fallback: "Unknown" })}</MobileField>
                      <MobileField label="Processed">{formatDateTime(entry.processed_at, { timeZone, fallback: "Not processed" })}</MobileField>
                    </dl>
                    <div className="mt-4">
                      <EntryDetails entry={entry} timeZone={timeZone} />
                    </div>
                  </MobileDisclosureCard>
                ))}
              </MobileCardList>
            )}
          >
            <Table>
              <TableHead>
                <tr>
                  <th className="px-4 py-3 font-semibold">Event</th>
                  <th className="px-4 py-3 font-semibold">Repository</th>
                  <th className="px-4 py-3 font-semibold">Reference</th>
                  <th className="px-4 py-3 font-semibold">Attempts</th>
                  <th className="px-4 py-3 font-semibold">Received</th>
                  <th className="px-4 py-3 font-semibold">Details</th>
                </tr>
              </TableHead>
              <TableBody>
                {payload.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="px-4 py-4 align-top">
                      <div className="flex flex-col gap-2">
                        <span className="font-semibold text-white">#{entry.id} {entry.action}</span>
                        <Badge tone={statusTone(entry.status)}>{entry.status}</Badge>
                      </div>
                    </td>
                    <td className="max-w-xs px-4 py-4 align-top">
                      <span className="break-all text-slate-200">{entry.repository_name}</span>
                    </td>
                    <td className="max-w-xs px-4 py-4 align-top">
                      <span className="break-all font-mono text-xs text-slate-300">{compactReference(entry)}</span>
                    </td>
                    <td className="px-4 py-4 align-top text-slate-300">{entry.attempts}</td>
                    <td className="px-4 py-4 align-top text-slate-300">
                      {formatDateTime(entry.received_at, { timeZone, fallback: "Unknown" })}
                    </td>
                    <td className="min-w-80 px-4 py-4 align-top">
                      <Disclosure titleClosed="Review" titleOpen="Hide">
                        <div className="px-4 py-4">
                          <EntryDetails entry={entry} timeZone={timeZone} />
                        </div>
                      </Disclosure>
                    </td>
                  </tr>
                ))}
              </TableBody>
            </Table>
          </TableShell>
        ) : (
          <EmptyState
            title="No inbox entries"
            description="No registry notifications match the current filter."
          />
        )}
        <Pagination
          page={payload.pagination.page}
          pageSize={payload.pagination.page_size}
          total={payload.pagination.total}
          label="entries"
          hrefForPage={(targetPage) => buildPageHref(validStatus, targetPage)}
        />
      </MobileCollapsiblePanel>
    </div>
  );
}
