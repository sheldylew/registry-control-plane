import Link from "next/link";

import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import Disclosure from "@/app/components/ui/disclosure";
import EmptyState from "@/app/components/ui/empty-state";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { formatDateTime } from "@/app/lib/date-format";
import Pagination from "@/app/components/ui/pagination";
import { apiFetch } from "@/app/lib/server-api";
import { getUiTimezone } from "@/app/lib/ui-settings";

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
  const timeZone = await getUiTimezone();
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
      <Panel as="section" className="p-6">
        <PanelHeader
          eyebrow="Audit log"
          title="Identity, token, and registry events"
          action={<Badge>Page {payload.pagination.page}</Badge>}
        />
        <div className="mt-5 flex flex-wrap gap-3 text-sm">
          <Button
            as={Link}
            href="/admin/audit"
            prefetch={false}
            variant="secondary"
          >
            Clear filters
          </Button>
          {actor ? (
            <Badge tone="cyan">actor={actor}</Badge>
          ) : null}
          {repo ? (
            <Badge tone="cyan">repo={repo}</Badge>
          ) : null}
        </div>
      </Panel>

      <Panel as="section" className="p-6">
        <div className="space-y-4">
          {payload.events.length ? (
            payload.events.map((event) => (
              <article key={event.id} className="rounded-lg border border-white/10 bg-slate-950/60 p-5">
                <div>
                  <p className="text-sm font-semibold text-white">{event.action}</p>
                  <p className="mt-2 text-sm text-slate-400">{formatDateTime(event.created_at, { timeZone })}</p>
                </div>
                <div className="mt-4">
                  <Disclosure titleClosed="View details" titleOpen="Hide details">
                    <div className="space-y-4 px-4 py-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="flex flex-wrap items-center gap-3">
                          <Badge>{event.actor_label || event.actor_type}</Badge>
                          {event.metadata_json?.repo ? (
                            <Link
                              href={`/admin/audit?repo=${encodeURIComponent(event.metadata_json.repo)}`}
                              prefetch={false}
                              className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300 transition hover:border-cyan-400/40 hover:text-white"
                            >
                              {event.metadata_json.repo}
                            </Link>
                          ) : null}
                        </div>
                        {event.actor_label && event.actor_label !== event.actor_type ? (
                          <Link
                            href={`/admin/audit?actor=${encodeURIComponent(event.actor_label)}`}
                            prefetch={false}
                            className="rounded-md border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300 transition hover:border-cyan-400/40 hover:text-white"
                          >
                            Filter actor
                          </Link>
                        ) : null}
                      </div>
                      <pre className="overflow-x-auto rounded-lg border border-white/10 bg-slate-950 px-4 py-4 text-xs text-slate-200">
                        {JSON.stringify(event.metadata_json || {}, null, 2)}
                      </pre>
                    </div>
                  </Disclosure>
                </div>
              </article>
            ))
          ) : (
            <EmptyState
              title="No audit events"
              description="No audit events matched the current filters."
            />
          )}
        </div>
        <Pagination
          page={payload.pagination.page}
          pageSize={payload.pagination.page_size}
          total={payload.pagination.total}
          label="events"
          hrefForPage={(targetPage) => buildPageHref({ actor, repo, page: targetPage })}
        />
      </Panel>
    </div>
  );
}
