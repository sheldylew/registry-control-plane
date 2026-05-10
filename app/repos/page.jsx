import Link from "next/link";

import Badge from "@/app/components/ui/badge";
import EmptyState from "@/app/components/ui/empty-state";
import Pagination from "@/app/components/ui/pagination";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { apiFetch } from "@/app/lib/server-api";

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

export default async function ReposPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(buildApiPath(page));
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load repositories.");
  }

  return (
    <div className="space-y-6">
      <Panel className="p-6">
        <PanelHeader
          title="Repositories"
          description="Browse the repositories you are allowed to pull, then inspect tags and manifests from the control plane."
        />
      </Panel>

      <Panel className="p-6">
        <PanelHeader
          title="Visible repositories"
          action={<Badge tone="cyan">{payload.pagination.total} visible</Badge>}
        />

        {payload.repos.length ? (
          <ul className="mt-4 divide-y divide-white/10 overflow-hidden rounded-lg border border-white/10 bg-slate-950/50">
            {payload.repos.map((repo) => (
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
        ) : (
          <div className="mt-6">
            <EmptyState
              title="No visible repositories"
              description="No repositories are visible for this account yet."
            />
          </div>
        )}
        <Pagination
          page={payload.pagination.page}
          pageSize={payload.pagination.page_size}
          total={payload.pagination.total}
          label="repositories"
          hrefForPage={buildPageHref}
        />
      </Panel>
    </div>
  );
}
