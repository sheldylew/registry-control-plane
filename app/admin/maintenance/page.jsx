import MaintenancePanel from "@/app/components/maintenance-panel";
import Disclosure from "@/app/components/ui/disclosure";
import Pagination from "@/app/components/ui/pagination";
import { apiFetch } from "@/app/lib/server-api";

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

function formatDate(value) {
  if (!value) {
    return "Pending";
  }
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) {
    return "Unknown";
  }
  return target.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
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
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(`/api/admin/maintenance?page=${page}`);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load maintenance status.");
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <article className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
          <p className="text-sm font-medium text-slate-300">Registry status</p>
          <p className="mt-4 text-3xl font-semibold text-white">{payload.registry_status}</p>
        </article>
        <article className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
          <p className="text-sm font-medium text-slate-300">Storage usage</p>
          <p className="mt-4 text-3xl font-semibold text-white">{formatBytes(payload.storage_usage_bytes)}</p>
        </article>
        <article className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
          <p className="text-sm font-medium text-slate-300">Last job</p>
          <p className="mt-4 text-3xl font-semibold capitalize text-white">
            {payload.last_job ? payload.last_job.status : "None"}
          </p>
          <p className="mt-2 text-sm text-slate-400">
            {payload.last_job ? summarizeMode(payload.last_job) : "No maintenance jobs yet"}
          </p>
        </article>
      </section>

      <MaintenancePanel logRetentionDays={payload.log_retention_days} />

      <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.22em] text-cyan-300">
              Job history
            </p>
            <h2 className="mt-3 text-2xl font-semibold text-white">Recent maintenance jobs</h2>
          </div>
          <span className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.16em] text-slate-300">
            Page {payload.pagination.page}
          </span>
        </div>
        <div className="mt-6 space-y-4">
          {payload.jobs.length ? (
            payload.jobs.map((job) => (
              <article key={job.id} className="rounded-2xl border border-white/10 bg-slate-950/60 p-5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <p className="text-sm font-semibold text-white">Job #{job.id}</p>
                      <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs uppercase tracking-[0.16em] text-slate-300">
                        {summarizeMode(job)}
                      </span>
                      <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs uppercase tracking-[0.16em] text-slate-300">
                        {job.status}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-slate-400">
                      Started {formatDate(job.started_at)}. Finished {formatDate(job.finished_at)}.
                    </p>
                    <p className="mt-2 text-sm text-slate-400">
                      Before: {formatBytes(job.bytes_before)}. After: {formatBytes(job.bytes_after)}.
                    </p>
                  </div>
                  {job.error ? (
                    <p className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                      {job.error}
                    </p>
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
            <p className="text-sm text-slate-300">No maintenance jobs recorded yet.</p>
          )}
        </div>
        <Pagination
          page={payload.pagination.page}
          pageSize={payload.pagination.page_size}
          total={payload.pagination.total}
          label="jobs"
          hrefForPage={buildPageHref}
        />
      </section>
    </div>
  );
}
