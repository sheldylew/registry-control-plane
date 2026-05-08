import Link from "next/link";

import Badge from "@/app/components/ui/badge";
import EmptyState from "@/app/components/ui/empty-state";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { apiFetch } from "@/app/lib/server-api";

export default async function ReposPage() {
  const response = await apiFetch("/api/repos");
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
          action={<Badge tone="cyan">{payload.repos.length} visible</Badge>}
        />

        {payload.repos.length ? (
          <ul className="mt-4 grid gap-4 md:grid-cols-2">
            {payload.repos.map((repo) => (
              <li key={repo.name}>
                <Link
                  href={`/repos/${encodeURIComponent(repo.name)}`}
                  className="block rounded-lg border border-white/10 bg-slate-950/70 px-5 py-5 transition hover:border-cyan-400/40 hover:bg-slate-950"
                >
                  <p className="text-lg font-semibold text-white">{repo.name}</p>
                  <p className="mt-2 text-sm text-slate-400">Open tags and manifest details</p>
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
      </Panel>
    </div>
  );
}
