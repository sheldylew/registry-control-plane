import Link from "next/link";

import Disclosure from "@/app/components/ui/disclosure";
import Pagination from "@/app/components/ui/pagination";
import { apiFetch } from "@/app/lib/server-api";

function formatDate(value) {
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

function buildApiPath(actor, repo, page) {
  const params = new URLSearchParams();
  if (actor) {
    params.set("actor", actor);
  }
  if (repo) {
    params.set("repo", repo);
  }
  params.set("page", String(page));
  return `/api/admin/audit?${params.toString()}`;
}

function buildPageHref({ actor, repo, page }) {
  const params = new URLSearchParams();
  if (actor) {
    params.set("actor", actor);
  }
  if (repo) {
    params.set("repo", repo);
  }
  if (page > 1) {
    params.set("page", String(page));
  }
  const query = params.toString();
  return query ? `/admin/audit?${query}` : "/admin/audit";
}

export default async function AdminAuditPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const actor = resolvedSearchParams?.actor || "";
  const repo = resolvedSearchParams?.repo || "";
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(buildApiPath(actor, repo, page));
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load audit log.");
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.22em] text-cyan-300">
              Audit log
            </p>
            <h2 className="mt-3 text-2xl font-semibold text-white">Identity, token, and registry events</h2>
          </div>
          <span className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.16em] text-slate-300">
            Page {payload.pagination.page}
          </span>
        </div>
        <div className="mt-5 flex flex-wrap gap-3 text-sm">
          <Link
            href="/admin/audit"
            className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-slate-200 transition hover:border-cyan-400/40 hover:text-white"
          >
            Clear filters
          </Link>
          {actor ? (
            <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-cyan-100">
              actor={actor}
            </span>
          ) : null}
          {repo ? (
            <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-cyan-100">
              repo={repo}
            </span>
          ) : null}
        </div>
      </section>

      <section className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <div className="space-y-4">
          {payload.events.length ? (
            payload.events.map((event) => (
              <article key={event.id} className="rounded-2xl border border-white/10 bg-slate-950/60 p-5">
                <div>
                  <p className="text-sm font-semibold text-white">{event.action}</p>
                  <p className="mt-2 text-sm text-slate-400">{formatDate(event.created_at)}</p>
                </div>
                <div className="mt-4">
                  <Disclosure titleClosed="View details" titleOpen="Hide details">
                    <div className="space-y-4 px-4 py-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="flex flex-wrap items-center gap-3">
                          <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs uppercase tracking-[0.16em] text-slate-300">
                            {event.actor_label || event.actor_type}
                          </span>
                          {event.metadata_json?.repo ? (
                            <Link
                              href={`/admin/audit?repo=${encodeURIComponent(event.metadata_json.repo)}`}
                              className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300 transition hover:border-cyan-400/40 hover:text-white"
                            >
                              {event.metadata_json.repo}
                            </Link>
                          ) : null}
                        </div>
                        {event.actor_label && event.actor_label !== event.actor_type ? (
                          <Link
                            href={`/admin/audit?actor=${encodeURIComponent(event.actor_label)}`}
                            className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300 transition hover:border-cyan-400/40 hover:text-white"
                          >
                            Filter actor
                          </Link>
                        ) : null}
                      </div>
                      <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950 px-4 py-4 text-xs text-slate-200">
                        {JSON.stringify(event.metadata_json || {}, null, 2)}
                      </pre>
                    </div>
                  </Disclosure>
                </div>
              </article>
            ))
          ) : (
            <p className="text-sm text-slate-300">No audit events matched the current filters.</p>
          )}
        </div>
        <Pagination
          page={payload.pagination.page}
          pageSize={payload.pagination.page_size}
          total={payload.pagination.total}
          label="events"
          hrefForPage={(targetPage) => buildPageHref({ actor, repo, page: targetPage })}
        />
      </section>
    </div>
  );
}
