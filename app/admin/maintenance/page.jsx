import MaintenancePanel from "@/app/components/maintenance-panel";
import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Disclosure from "@/app/components/ui/disclosure";
import EmptyState from "@/app/components/ui/empty-state";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import Pagination from "@/app/components/ui/pagination";
import StatCard from "@/app/components/ui/stat-card";
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

function buildPageHref(page) {
  if (page <= 1) {
    return "/admin/maintenance";
  }
  return `/admin/maintenance?page=${page}`;
}

export default async function AdminMaintenancePage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const timeZone = await getUiTimezone();
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(`/api/admin/maintenance?page=${page}`);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load maintenance status.");
  }

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
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Registry status" value={payload.registry_status} />
        <StatCard label="Storage usage" value={formatBytes(payload.storage_usage_bytes)} />
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
        />
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
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
      </section>

      <MaintenancePanel logRetentionDays={payload.log_retention_days} />

      <Panel as="section" className="p-6">
        <PanelHeader
          eyebrow="Job history"
          title="Recent maintenance jobs"
          action={<Badge>Page {payload.pagination.page}</Badge>}
        />
        <div className="mt-6 space-y-4">
          {payload.jobs.length ? (
            payload.jobs.map((job) => (
              <article key={job.id} className="rounded-lg border border-white/10 bg-slate-950/60 p-5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <p className="text-sm font-semibold text-white">Job #{job.id}</p>
                      <Badge>{summarizeMode(job)}</Badge>
                      <Badge tone={job.status === "failed" ? "rose" : "slate"}>{job.status}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-slate-400">
                      Started {formatDateTime(job.started_at, { timeZone, fallback: "Pending" })}. Finished {formatDateTime(job.finished_at, { timeZone, fallback: "Pending" })}.
                    </p>
                    <p className="mt-2 text-sm text-slate-400">
                      Before: {formatBytes(job.bytes_before)}. After: {formatBytes(job.bytes_after)}.
                    </p>
                  </div>
                  {job.error ? (
                    <Alert tone="rose">{job.error}</Alert>
                  ) : null}
                </div>
                {job.log_output ? (
                  <div className="mt-4">
                    <Disclosure
                      titleClosed="View output"
                      titleOpen="Hide output"
                      meta={`${job.log_output.split("\n").filter(Boolean).length} lines`}
                    >
                      <pre className="overflow-x-auto border-t border-white/10 px-4 py-4 text-xs text-slate-200">
                        {job.log_output}
                      </pre>
                    </Disclosure>
                  </div>
                ) : null}
              </article>
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
      </Panel>

      <Panel as="section" className="p-6">
        <PanelHeader
          eyebrow="Registry state"
          title="Recent registry state rebuild jobs"
          action={<Badge>{payload.rebuild_jobs.length} shown</Badge>}
        />
        <div className="mt-6 space-y-4">
          {payload.rebuild_jobs.length ? (
            payload.rebuild_jobs.map((job) => (
              <article key={job.id} className="rounded-lg border border-white/10 bg-slate-950/60 p-5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <p className="text-sm font-semibold text-white">Rebuild #{job.id}</p>
                      <Badge tone={job.status === "failed" ? "rose" : "slate"}>{job.status}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-slate-400">
                      Repositories: {job.repositories_scanned}. Tags: {job.tags_scanned}. Deleted tags: {job.tags_deleted}.
                    </p>
                    <p className="mt-2 text-sm text-slate-400">
                      Started {formatDateTime(job.started_at, { timeZone, fallback: "Pending" })}. Finished {formatDateTime(job.finished_at, { timeZone, fallback: "Pending" })}.
                    </p>
                  </div>
                  {job.error ? (
                    <Alert tone="rose">{job.error}</Alert>
                  ) : null}
                </div>
                {job.log_output ? (
                  <div className="mt-4">
                    <Disclosure
                      titleClosed="View output"
                      titleOpen="Hide output"
                      meta={`${job.log_output.split("\n").filter(Boolean).length} lines`}
                    >
                      <pre className="overflow-x-auto border-t border-white/10 px-4 py-4 text-xs text-slate-200">
                        {job.log_output}
                      </pre>
                    </Disclosure>
                  </div>
                ) : null}
              </article>
            ))
          ) : (
            <EmptyState
              title="No rebuild jobs"
              description="No registry state rebuild jobs recorded yet."
            />
          )}
        </div>
      </Panel>
    </div>
  );
}
