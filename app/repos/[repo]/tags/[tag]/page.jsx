import Link from "next/link";
import { notFound } from "next/navigation";

import RepoDeletePanel from "@/app/components/repo-delete-panel";
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

export default async function RepoTagDetailPage({ params }) {
  const resolvedParams = await params;
  const repoPath = decodeURIComponent(resolvedParams.repo);
  const response = await apiFetch(`/api/repos/${repoPath}/tags/${encodeURIComponent(resolvedParams.tag)}`);

  if (response.status === 404) {
    notFound();
  }

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load manifest details.");
  }

  const { manifest } = payload;

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-cyan-300">Manifest</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">
              {manifest.name}:{manifest.tag}
            </h2>
          </div>
          {payload.can_delete_tag ? (
            <Link
              href="/admin/maintenance"
              className="inline-flex rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white"
            >
              Garbage collection
            </Link>
          ) : null}
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Digest</p>
            <p className="mt-2 break-all text-sm text-slate-100">{manifest.digest || "Unavailable"}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Media Type</p>
            <p className="mt-2 break-all text-sm text-slate-100">{manifest.media_type || "Unavailable"}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Config Digest</p>
            <p className="mt-2 break-all text-sm text-slate-100">{manifest.config_digest || "Unavailable"}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Estimated Size</p>
            <p className="mt-2 text-sm text-slate-100">{formatBytes(manifest.total_size)}</p>
          </div>
        </div>
      </div>

      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <h3 className="text-xl font-semibold text-white">Layers</h3>
        {manifest.layers.length ? (
          <ul className="mt-4 space-y-3">
            {manifest.layers.map((layer) => (
              <li key={layer.digest} className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
                <p className="break-all text-sm font-medium text-white">{layer.digest}</p>
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">{layer.mediaType}</p>
                <p className="mt-2 text-sm text-slate-300">{formatBytes(layer.size || 0)}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 text-sm text-slate-300">This manifest did not expose OCI layer entries.</p>
        )}
      </div>

      {payload.can_delete_tag ? (
        <RepoDeletePanel
          title="Delete tag"
          description="This resolves the tag to its manifest digest and deletes that manifest from the registry. Disk space is not reclaimed until registry garbage collection runs."
          confirmationValue={`${manifest.name}:${manifest.tag}`}
          requireConfirmation={false}
          endpoint={`/api/repos/${encodeURIComponent(manifest.name)}/tags/${encodeURIComponent(manifest.tag)}/delete`}
          buttonLabel="Delete tag"
          successLabel="Deleting..."
        />
      ) : null}
    </div>
  );
}
