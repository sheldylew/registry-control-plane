import { Fragment } from "react";
import Link from "next/link";

import MaintenancePanel from "@/app/components/maintenance-panel";
import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import FloatingButtonGroup from "@/app/components/ui/floating-button-group";
import JobOutputDisclosure from "@/app/components/job-output-disclosure";
import { MobileCollapsiblePanel, Panel, PanelHeader } from "@/app/components/ui/panel";
import Pagination from "@/app/components/ui/pagination";
import StatCard from "@/app/components/ui/stat-card";
import { MobileDisclosureCard, MobileField } from "@/app/components/ui/table";
import { formatDateTime } from "@/app/lib/date-format";
import { apiFetch } from "@/app/lib/server-api";
import { getUiTimezone } from "@/app/lib/ui-settings";

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

function summarizeMode(job) {
  if (job.dry_run) {
    return "Analyze";
  }
  if (job.delete_untagged || job.prune_empty_dirs) {
    return "Aggressive";
  }
  return "Standard";
}

function summarizeModeTone(job) {
  if (job.dry_run) {
    return "emerald";
  }
  if (job.delete_untagged || job.prune_empty_dirs) {
    return "amber";
  }
  return "cyan";
}

function buildPageHref(page) {
  if (page <= 1) {
    return "/admin/maintenance";
  }
  return `/admin/maintenance?page=${page}`;
}

export default async function AdminMaintenancePage({ searchParams }) {
  const [resolvedSearchParams, timeZone] = await Promise.all([
    searchParams,
    getUiTimezone(),
  ]);
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(`/api/admin/maintenance?page=${page}`);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load maintenance status.");
  }

  const storageUsageDetail = payload.storage_usage_measured_at
    ? `${payload.storage_usage_stale ? "Last measured" : "Measured"} ${formatDateTime(payload.storage_usage_measured_at, { timeZone, fallback: "Unknown" })}.`
    : "Waiting for the first background measurement.";
  const manifestSummaryDetail = payload.cache.summaries_total
    ? `${payload.cache.repositories_total} repositories. First refreshed ${formatDateTime(payload.cache.oldest_cached_at, { timeZone, fallback: "Unknown" })}.`
    : "No manifest summaries recorded yet.";
  const manifestFreshnessDetail = payload.cache.newest_last_seen_at
    ? `Newest refresh ${formatDateTime(payload.cache.newest_last_seen_at, { timeZone, fallback: "Unknown" })}.`
    : "No manifest summary refreshes recorded yet.";
  const lastRebuildDetail = payload.registry_state.last_rebuild
    ? `Finished ${formatDateTime(payload.registry_state.last_rebuild.finished_at, { timeZone, fallback: "Pending" })}.`
    : "No rebuild jobs yet.";

  return (
    <div className="space-y-6">
      <FloatingButtonGroup
        items={[
          { href: "#maintenance-actions", label: "Actions" },
          { href: "#maintenance-jobs", label: "Jobs" },
          { href: "#maintenance-rebuilds", label: "Rebuilds" },
        ]}
      />

      <Panel as="section" className="p-4 sm:p-6">
        <PanelHeader
          eyebrow="Maintenance status"
          title="Registry health and state"
          description="Review storage, manifest cache, registry state, and recent maintenance outcomes before running jobs."
          action={(
            <Button as={Link} href="/admin/maintenance/inbox?status=failed" prefetch={false} variant="secondary" className="w-full sm:w-auto">
              Open inbox
            </Button>
          )}
        />
        <div className="mt-5 grid gap-3 sm:mt-6 sm:gap-4 md:grid-cols-3 xl:grid-cols-5">
          <StatCard label="Registry status" value={payload.registry_status} />
          <StatCard
            label="Registry disk used"
            value={formatBytes(payload.storage_usage_bytes)}
            detail={storageUsageDetail}
            badge={payload.storage_usage_stale ? "Stale" : null}
            badgeTone="amber"
          />
          <StatCard
            label="Manifest summaries"
            value={payload.cache.summaries_total}
            detail={manifestSummaryDetail}
            tone="cyan"
          />
          <StatCard
            label="Refreshed in 24h"
            value={payload.cache.seen_last_24h}
            detail={manifestFreshnessDetail}
            tone="emerald"
          />
          <StatCard
            label="Last job"
            value={payload.last_job ? payload.last_job.status : "None"}
            detail={payload.last_job ? summarizeMode(payload.last_job) : "No maintenance jobs yet"}
            detailBadge={Boolean(payload.last_job)}
            detailBadgeTone={payload.last_job ? summarizeModeTone(payload.last_job) : "slate"}
          />
          <StatCard
            label="Active repositories"
            value={payload.registry_state.active_repositories}
            detail="Backed by the app database."
            tone="cyan"
          />
          <StatCard
            label="Active tags"
            value={payload.registry_state.active_tags}
            detail="Available without registry scans."
            tone="emerald"
          />
          <StatCard
            label="Inbox queued"
            value={payload.registry_state.inbox_queued}
            detail="Registry events awaiting processing."
          />
          <StatCard
            label="Inbox failed"
            value={payload.registry_state.inbox_failed}
            detail="Needs rebuild or retry review."
            tone={payload.registry_state.inbox_failed ? "rose" : "slate"}
          />
          <StatCard
            label="Last rebuild"
            value={payload.registry_state.last_rebuild ? payload.registry_state.last_rebuild.status : "None"}
            detail={lastRebuildDetail}
          />
        </div>
      </Panel>

      <MaintenancePanel logRetentionDays={payload.log_retention_days} />

      <MobileCollapsiblePanel
        id="maintenance-jobs"
        as="section"
        className="scroll-mt-24 p-4 sm:p-6"
        eyebrow="Job history"
        title="Recent maintenance jobs"
        summaryMeta={`${payload.pagination.total} jobs`}
        openLabel="Open job history"
        hideLabel="Hide job history"
      >
        <PanelHeader
          eyebrow="Job history"
          title="Recent maintenance jobs"
          action={<Badge>Page {payload.pagination.page}</Badge>}
        />
        <div className="mt-6 space-y-4">
          {payload.jobs.length ? (
            payload.jobs.map((job) => (
              <Fragment key={job.id}>
              <MobileDisclosureCard
                className="lg:hidden"
                summary={(
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-white">Job #{job.id}</p>
                      <Badge>{summarizeMode(job)}</Badge>
                      <Badge tone={job.status === "failed" ? "rose" : "slate"}>{job.status}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">
                      Started {formatDateTime(job.started_at, { timeZone, fallback: "Pending" })}
                    </p>
                  </div>
                )}
              >
                <dl className="grid gap-3">
                  <MobileField label="Finished">{formatDateTime(job.finished_at, { timeZone, fallback: "Pending" })}</MobileField>
                  <MobileField label="Before">{formatBytes(job.bytes_before)}</MobileField>
                  <MobileField label="After">{formatBytes(job.bytes_after)}</MobileField>
                </dl>
                {job.error ? (
                  <Alert tone="rose" className="mt-4">{job.error}</Alert>
                ) : null}
                {job.log_output_available ? (
                  <div className="mt-4">
                    <JobOutputDisclosure
                      endpoint={`/api/admin/maintenance/jobs/${job.id}/log`}
                      lineCount={job.log_output_line_count}
                    />
                  </div>
                ) : null}
              </MobileDisclosureCard>
              <article className="hidden rounded-lg border border-white/10 bg-slate-950/60 p-4 sm:p-5 lg:block">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                      <p className="text-sm font-semibold text-white">Job #{job.id}</p>
                      <Badge>{summarizeMode(job)}</Badge>
                      <Badge tone={job.status === "failed" ? "rose" : "slate"}>{job.status}</Badge>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-400">
                      Started {formatDateTime(job.started_at, { timeZone, fallback: "Pending" })}. Finished {formatDateTime(job.finished_at, { timeZone, fallback: "Pending" })}.
                    </p>
                    <p className="mt-2 rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-300 sm:border-0 sm:bg-transparent sm:px-0 sm:py-0 sm:text-slate-400">
                      Before: {formatBytes(job.bytes_before)}. After: {formatBytes(job.bytes_after)}.
                    </p>
                  </div>
                  {job.error ? (
                    <Alert tone="rose">{job.error}</Alert>
                  ) : null}
                </div>
                {job.log_output_available ? (
                  <div className="mt-4">
                    <JobOutputDisclosure
                      endpoint={`/api/admin/maintenance/jobs/${job.id}/log`}
                      lineCount={job.log_output_line_count}
                    />
                  </div>
                ) : null}
              </article>
              </Fragment>
            ))
          ) : (
            <EmptyState
              title="No maintenance jobs"
              description="No maintenance jobs recorded yet."
            />
          )}
        </div>
        <Pagination
          page={payload.pagination.page}
          pageSize={payload.pagination.page_size}
          total={payload.pagination.total}
          label="jobs"
          hrefForPage={buildPageHref}
        />
      </MobileCollapsiblePanel>

      <MobileCollapsiblePanel
        id="maintenance-rebuilds"
        as="section"
        className="scroll-mt-24 p-4 sm:p-6"
        eyebrow="Registry state"
        title="Recent registry state rebuild jobs"
        summaryMeta={`${payload.rebuild_jobs.length} shown`}
        openLabel="Open rebuild jobs"
        hideLabel="Hide rebuild jobs"
      >
        <PanelHeader
          eyebrow="Registry state"
          title="Recent registry state rebuild jobs"
          action={<Badge>{payload.rebuild_jobs.length} shown</Badge>}
        />
        <div className="mt-6 space-y-4">
          {payload.rebuild_jobs.length ? (
            payload.rebuild_jobs.map((job) => (
              <Fragment key={job.id}>
              <MobileDisclosureCard
                className="lg:hidden"
                summary={(
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-white">Rebuild #{job.id}</p>
                      <Badge tone={job.status === "failed" ? "rose" : "slate"}>{job.status}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">
                      {job.repositories_scanned} repositories, {job.tags_scanned} tags
                    </p>
                  </div>
                )}
              >
                <dl className="grid gap-3">
                  <MobileField label="Deleted tags">{job.tags_deleted}</MobileField>
                  <MobileField label="Started">{formatDateTime(job.started_at, { timeZone, fallback: "Pending" })}</MobileField>
                  <MobileField label="Finished">{formatDateTime(job.finished_at, { timeZone, fallback: "Pending" })}</MobileField>
                </dl>
                {job.error ? (
                  <Alert tone="rose" className="mt-4">{job.error}</Alert>
                ) : null}
                {job.log_output_available ? (
                  <div className="mt-4">
                    <JobOutputDisclosure
                      endpoint={`/api/admin/maintenance/cache/rebuild/${job.id}/log`}
                      lineCount={job.log_output_line_count}
                    />
                  </div>
                ) : null}
              </MobileDisclosureCard>
              <article className="hidden rounded-lg border border-white/10 bg-slate-950/60 p-4 sm:p-5 lg:block">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                      <p className="text-sm font-semibold text-white">Rebuild #{job.id}</p>
                      <Badge tone={job.status === "failed" ? "rose" : "slate"}>{job.status}</Badge>
                    </div>
                    <p className="mt-2 rounded-md border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-300 sm:border-0 sm:bg-transparent sm:px-0 sm:py-0 sm:text-slate-400">
                      Repositories: {job.repositories_scanned}. Tags: {job.tags_scanned}. Deleted tags: {job.tags_deleted}.
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-400">
                      Started {formatDateTime(job.started_at, { timeZone, fallback: "Pending" })}. Finished {formatDateTime(job.finished_at, { timeZone, fallback: "Pending" })}.
                    </p>
                  </div>
                  {job.error ? (
                    <Alert tone="rose">{job.error}</Alert>
                  ) : null}
                </div>
                {job.log_output_available ? (
                  <div className="mt-4">
                    <JobOutputDisclosure
                      endpoint={`/api/admin/maintenance/cache/rebuild/${job.id}/log`}
                      lineCount={job.log_output_line_count}
                    />
                  </div>
                ) : null}
              </article>
              </Fragment>
            ))
          ) : (
            <EmptyState
              title="No rebuild jobs"
              description="No registry state rebuild jobs recorded yet."
            />
          )}
        </div>
      </MobileCollapsiblePanel>
    </div>
  );
}
