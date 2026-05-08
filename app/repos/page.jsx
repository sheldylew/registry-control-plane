import Link from "next/link";

import { apiFetch } from "@/app/lib/server-api";

export default async function ReposPage() {
  const response = await apiFetch("/api/repos");
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load repositories.");
  }

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <h2 className="text-3xl font-semibold text-white">Repositories</h2>
        <p className="mt-3 text-sm leading-7 text-slate-300">
          Browse the repositories you are allowed to pull, then inspect tags and manifests from the control plane.
        </p>
      </div>

      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-semibold text-white">Visible repositories</h3>
          <p className="text-sm text-slate-400">{payload.repos.length} visible</p>
        </div>

        {payload.repos.length ? (
          <ul className="mt-4 grid gap-4 md:grid-cols-2">
            {payload.repos.map((repo) => (
              <li key={repo.name}>
                <Link
                  href={`/repos/${encodeURIComponent(repo.name)}`}
                  className="block rounded-2xl border border-white/10 bg-slate-950/70 px-5 py-5 transition hover:border-cyan-400/40 hover:bg-slate-950"
                >
                  <p className="text-lg font-semibold text-white">{repo.name}</p>
                  <p className="mt-2 text-sm text-slate-400">Open tags and manifest details</p>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 text-sm text-slate-300">No repositories are visible for this account yet.</p>
        )}
      </div>
    </div>
  );
}
