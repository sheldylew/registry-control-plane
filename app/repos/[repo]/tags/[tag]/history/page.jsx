import Link from "next/link";
import { notFound } from "next/navigation";

import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
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
      <Panel className="p-6">
        <PanelHeader
          eyebrow="History"
          title={`${payload.repo}:${payload.tag}`}
          description="Inspect build history separately for each image variant behind this tag."
          action={(
            <Button
              as={Link}
              href={`/repos/${encodeURIComponent(payload.repo)}`}
              variant="secondary"
            >
              Back to repository
            </Button>
          )}
        />
      </Panel>

      {payload.variants.map((variant, index) => (
        <Panel as="section" key={`${variant.platform || "single"}-${index}`} className="p-6">
          <PanelHeader
            eyebrow="Variant"
            title={variant.platform ? formatPlatformLabel(variant.platform) : "Single image"}
            action={(
              <div className="flex flex-wrap gap-2">
                <Badge>Created: {formatDate(variant.created_at)}</Badge>
                <Badge tone="cyan">{variant.entry_count} entries</Badge>
              </div>
            )}
          />

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-white/10 bg-slate-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Manifest Digest</p>
              <p className="mt-2 break-all font-mono text-xs text-slate-100">{variant.manifest_digest || "Unavailable"}</p>
            </div>
            <div className="rounded-lg border border-white/10 bg-slate-950/70 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Config Digest</p>
              <p className="mt-2 break-all font-mono text-xs text-slate-100">{variant.config_digest || "Unavailable"}</p>
            </div>
          </div>

          {variant.entries.length ? (
            <ol className="mt-5 space-y-3">
              {variant.entries.map((entry, entryIndex) => (
                <li key={entryIndex} className="rounded-lg border border-white/10 bg-slate-950/70 p-4">
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
            <div className="mt-5">
              <EmptyState
                title="No history entries"
                description="No history entries were exposed by this image config."
              />
            </div>
          )}
        </Panel>
      ))}
    </div>
  );
}
