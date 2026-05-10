import Link from "next/link";
import { notFound } from "next/navigation";

import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import Pagination from "@/app/components/ui/pagination";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { Table, TableBody, TableHead, TableShell } from "@/app/components/ui/table";
import RepoDeletePanel from "@/app/components/repo-delete-panel";
import RepositoryVisibilityPanel from "@/app/components/repository-visibility-panel";
import { apiFetch } from "@/app/lib/server-api";

function buildApiPath(repoPath, page) {
  return `/api/repos/${repoPath}/tags?page=${String(page)}`;
}

function buildPageHref(repoPath, page) {
  const basePath = `/repos/${encodeURIComponent(repoPath)}`;
  if (page <= 1) {
    return basePath;
  }
  const params = new URLSearchParams();
  params.set("page", String(page));
  return `${basePath}?${params.toString()}`;
}

export default async function RepoDetailPage({ params, searchParams }) {
  const resolvedParams = await params;
  const resolvedSearchParams = await searchParams;
  const repoPath = decodeURIComponent(resolvedParams.repo);
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(buildApiPath(repoPath, page));

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
                  prefetch={false}
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
                    <th className="px-4 py-4 font-medium">Tag</th>
                    <th className="px-4 py-4 text-right font-medium">Actions</th>
                    {payload.can_delete_tag ? <th className="px-4 py-4 text-right font-medium">Delete</th> : null}
                  </tr>
                </TableHead>
                <TableBody>
                  {payload.tags.map((tag) => (
                    <tr key={tag.tag}>
                      <td className="px-4 py-4 align-top">
                        <Link
                          href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}`}
                          prefetch={false}
                          className="font-medium text-cyan-200 transition hover:text-cyan-100"
                        >
                          {tag.tag}
                        </Link>
                      </td>
                      <td className="px-4 py-4 align-top text-right">
                        <div className="flex justify-end gap-2">
                          <Link
                            href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}`}
                            prefetch={false}
                            className="inline-flex rounded-md border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-sm font-medium text-cyan-200 transition hover:border-cyan-300 hover:text-cyan-100"
                          >
                            Details
                          </Link>
                          <Link
                            href={`/repos/${encodeURIComponent(payload.repo)}/tags/${encodeURIComponent(tag.tag)}/history`}
                            prefetch={false}
                            className="inline-flex rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-cyan-400/40 hover:text-white"
                          >
                            History
                          </Link>
                        </div>
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
        <Pagination
          page={payload.pagination.page}
          pageSize={payload.pagination.page_size}
          total={payload.pagination.total}
          label="tags"
          hrefForPage={(page) => buildPageHref(payload.repo, page)}
        />
      </Panel>
    </div>
  );
}
