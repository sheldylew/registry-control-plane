import Link from "next/link";
import { notFound } from "next/navigation";
import { ClockIcon } from "@heroicons/react/24/outline";

import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { Table, TableBody, TableHead, TableShell } from "@/app/components/ui/table";
import RepoDeletePanel from "@/app/components/repo-delete-panel";
import RepositoryVisibilityPanel from "@/app/components/repository-visibility-panel";
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

function formatDigest(digest) {
  if (!digest) {
    return "Unavailable";
  }
  if (digest.length <= 24) {
    return digest;
  }
  return `${digest.slice(0, 18)}...${digest.slice(-12)}`;
}

function formatRelativeTime(value) {
  if (!value) {
    return "Unknown";
  }
  const target = new Date(value);
  const diffMs = Date.now() - target.getTime();
  if (Number.isNaN(diffMs)) {
    return "Unknown";
  }
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffHours < 1) {
    return "Less than 1h ago";
  }
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays}d ago`;
  }
  return target.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatPlatformLabel(value) {
  return value || "Unknown platform";
}

export default async function RepoDetailPage({ params }) {
  const resolvedParams = await params;
  const repoPath = decodeURIComponent(resolvedParams.repo);
  const response = await apiFetch(`/api/repos/${repoPath}/tags`);

  if (response.status === 404) {
    notFound();
  }

  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load repository tags.");
  }

  return (
    <div className="space-y-6">
      <Panel className="p-6">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,0.95fr)] xl:items-start">
          <PanelHeader
            eyebrow="Repository"
            title={payload.repo}
            description="Browse published tags and inspect manifest details without direct browser-to-registry calls."
          />
          {(payload.can_manage_visibility || payload.can_delete_tag || payload.can_prune_repository) ? (
            <div className="space-y-3">
              {payload.can_manage_visibility ? (
                <RepositoryVisibilityPanel
                  repositoryName={payload.repo}
                  initialVisibility={payload.visibility}
                />
              ) : null}
              {payload.can_delete_tag || payload.can_prune_repository ? (
                <Button
                  as={Link}
                  href="/admin/maintenance"
                  variant="secondary"
                  className="w-full justify-center"
                >
                  Garbage collection
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      </Panel>

      <Panel className="p-6">
        <PanelHeader title="Tags" action={<Badge tone="cyan">{payload.tags.length} total</Badge>} />
        {payload.tags.length ? (
          <div className="mt-4">
            <TableShell>
              <Table>
                <TableHead>
                  <tr>
                    <th className="px-4 py-4 font-medium">Created</th>
                    <th className="px-4 py-4 font-medium">Size</th>
                    <th className="px-4 py-4 font-medium">Content Digest</th>
                    <th className="px-4 py-4 text-center font-medium">Tag</th>
                    <th className="px-4 py-4 font-medium">Arch</th>
                    <th className="px-4 py-4 font-medium">History</th>
                    {payload.can_delete_tag ? <th className="px-4 py-4 text-right font-medium">Delete</th> : null}
                  </tr>
                </TableHead>
                <TableBody>
                  {payload.tags.map((tag) => (
                    <tr key={tag.tag}>
                      <td className="px-4 py-4 align-top text-slate-300">{formatRelativeTime(tag.created_at)}</td>
                      <td className="px-4 py-4 align-top text-slate-300">{formatBytes(tag.total_size)}</td>
                      <td className="px-4 py-4 align-top">
                        <div className="font-mono text-xs text-slate-200" title={tag.digest || "Unavailable"}>
                          {formatDigest(tag.digest)}
                        </div>
                      </td>
                      <td className="px-4 py-4 align-top text-center">
                        <Link
                          href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}`}
                          className="inline-flex rounded-md border border-cyan-400/30 bg-cyan-400/10 px-2 py-1 font-medium text-cyan-200 transition hover:border-cyan-300 hover:text-cyan-100"
                        >
                          {tag.tag}
                        </Link>
                      </td>
                      <td className="px-4 py-4 align-top">
                        <div className="flex flex-wrap gap-2">
                          {tag.architectures.length ? (
                            tag.architectures.map((arch) => (
                              <span
                                key={arch}
                                className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200"
                              >
                                {formatPlatformLabel(arch)}
                              </span>
                            ))
                          ) : (
                            <span className="text-slate-500">Unknown platform</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-4 align-top text-slate-300">
                        <Link
                          href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}/history`}
                          className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-white/10 bg-white/5 text-slate-200 transition hover:border-cyan-400/40 hover:text-white"
                          title={tag.history_count === null ? "View history" : `View ${tag.history_count} history entries`}
                          aria-label={tag.history_count === null ? "View history" : `View ${tag.history_count} history entries`}
                        >
                          <ClockIcon className="h-5 w-5" aria-hidden="true" />
                        </Link>
                      </td>
                      {payload.can_delete_tag ? (
                        <td className="px-4 py-4 align-top text-right">
                          <RepoDeletePanel
                            compact
                            title="Delete tag"
                            description="This resolves the tag to its manifest digest and deletes that manifest from the registry. Disk space is not reclaimed until registry garbage collection runs."
                            confirmationValue={`${payload.repo}:${tag.tag}`}
                            requireConfirmation={false}
                            endpoint={`/api/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}/delete`}
                            buttonLabel="Delete"
                            successLabel="Deleting..."
                          />
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </TableBody>
              </Table>
            </TableShell>
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            <EmptyState
              title="No tags returned"
              description="No tags were returned by the registry for this repository."
            />
            {payload.can_prune_repository ? (
              <RepoDeletePanel
                title="Delete empty repository"
                description="This removes the empty repository directory from registry storage. Use it only after all tags and manifests are gone."
                confirmationLabel="Type the repository name to confirm"
                confirmationValue={payload.repo}
                endpoint={`/api/repos/${encodeURIComponent(payload.repo)}/delete`}
                buttonLabel="Delete empty repository"
                successLabel="Deleting..."
              />
            ) : null}
          </div>
        )}
      </Panel>
    </div>
  );
}
