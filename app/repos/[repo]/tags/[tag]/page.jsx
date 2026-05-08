import Link from "next/link";
import { notFound } from "next/navigation";

import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
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
      <Panel className="p-6">
        <PanelHeader
          eyebrow="Manifest"
          title={`${manifest.name}:${manifest.tag}`}
          action={payload.can_delete_tag ? (
            <Button
              as={Link}
              href="/admin/maintenance"
              variant="secondary"
            >
              Garbage collection
            </Button>
          ) : null}
        />
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-white/10 bg-slate-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Digest</p>
            <p className="mt-2 break-all text-sm text-slate-100">{manifest.digest || "Unavailable"}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Media Type</p>
            <p className="mt-2 break-all text-sm text-slate-100">{manifest.media_type || "Unavailable"}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Config Digest</p>
            <p className="mt-2 break-all text-sm text-slate-100">{manifest.config_digest || "Unavailable"}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/70 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Estimated Size</p>
            <p className="mt-2 text-sm text-slate-100">{formatBytes(manifest.total_size)}</p>
          </div>
        </div>
      </Panel>

      <Panel className="p-6">
        <PanelHeader title="Layers" />
        {manifest.layers.length ? (
          <ul className="mt-4 space-y-3">
            {manifest.layers.map((layer) => (
              <li key={layer.digest} className="rounded-lg border border-white/10 bg-slate-950/70 p-4">
                <p className="break-all text-sm font-medium text-white">{layer.digest}</p>
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">{layer.mediaType}</p>
                <p className="mt-2 text-sm text-slate-300">{formatBytes(layer.size || 0)}</p>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-4">
            <EmptyState
              title="No layer entries"
              description="This manifest did not expose OCI layer entries."
            />
          </div>
        )}
      </Panel>

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
