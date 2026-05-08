import Link from "next/link";
import { notFound } from "next/navigation";

import { apiFetch } from "@/app/lib/server-api";

function formatDate(value) {
  if (!value) {
    return "Unknown";
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

function formatPlatformLabel(value) {
  return value || "Unknown platform";
}

export default async function RepoTagHistoryPage({ params }) {
  const resolvedParams = await params;
  const repoPath = decodeURIComponent(resolvedParams.repo);
  const response = await apiFetch(`/api/repos/${repoPath}/tags/${encodeURIComponent(resolvedParams.tag)}/history`);

  if (response.status === 404) {
    notFound();
  }

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load tag history.");
  }

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <p className="text-sm font-medium uppercase tracking-[0.2em] text-cyan-300">History</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">
          {payload.repo}:{payload.tag}
        </h2>
        <p className="mt-3 text-sm leading-7 text-slate-300">
          Inspect build history separately for each image variant behind this tag.
        </p>
        <Link
          href={`/repos/${encodeURIComponent(payload.repo)}`}
          className="mt-5 inline-flex rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white"
        >
          Back to repository
        </Link>
      </div>

      {payload.variants.map((variant, index) => (
        <section key={`${variant.platform || "single"}-${index}`} className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Variant</p>
              <h3 className="mt-2 text-2xl font-semibold text-white">
                {variant.platform ? formatPlatformLabel(variant.platform) : "Single image"}
              </h3>
            </div>
            <div className="text-sm text-slate-300">
              <p>Created: {formatDate(variant.created_at)}</p>
              <p>Entries: {variant.entry_count}</p>
            </div>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Manifest Digest</p>
              <p className="mt-2 break-all font-mono text-xs text-slate-100">{variant.manifest_digest || "Unavailable"}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Config Digest</p>
              <p className="mt-2 break-all font-mono text-xs text-slate-100">{variant.config_digest || "Unavailable"}</p>
            </div>
          </div>

          {variant.entries.length ? (
            <ol className="mt-5 space-y-3">
              {variant.entries.map((entry, entryIndex) => (
                <li key={entryIndex} className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <p className="text-sm font-medium text-white">Step {entryIndex + 1}</p>
                    <p className="text-xs text-slate-400">{formatDate(entry.created || null)}</p>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap break-words font-mono text-xs text-slate-200">
                    {entry.created_by || "No created_by metadata."}
                  </p>
                  {entry.comment ? (
                    <p className="mt-2 text-xs text-slate-400">{entry.comment}</p>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-5 text-sm text-slate-300">No history entries were exposed by this image config.</p>
          )}
        </section>
      ))}
    </div>
  );
}
