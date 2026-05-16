import Link from "next/link";
import { notFound } from "next/navigation";

import Button from "@/app/components/ui/button";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import RepositoryTagsPanel from "@/app/components/repository-tags-panel";
import RepositoryVisibilityPanel from "@/app/components/repository-visibility-panel";
import { apiFetch } from "@/app/lib/server-api";
import { getUiTimezone } from "@/app/lib/ui-settings";

function buildApiPath(repoPath, page, sort, direction) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("sort", sort);
  params.set("direction", direction);
  return `/api/repos/${repoPath}/tags?${params.toString()}`;
}

export default async function RepoDetailPage({ params, searchParams }) {
  const timeZone = await getUiTimezone();
  const resolvedParams = await params;
  const resolvedSearchParams = await searchParams;
  const repoPath = decodeURIComponent(resolvedParams.repo);
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const sort = ["created", "tag"].includes(resolvedSearchParams?.sort) ? resolvedSearchParams.sort : "created";
  const direction = ["asc", "desc"].includes(resolvedSearchParams?.direction) ? resolvedSearchParams.direction : "desc";
  const response = await apiFetch(buildApiPath(repoPath, page, sort, direction));

  if (response.status === 404) {
    notFound();
  }

  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load repository tags.");
  }

  return (
    <div className="space-y-6">
      <Panel className="p-4 sm:p-6">
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

      <RepositoryTagsPanel payload={payload} timeZone={timeZone} />
    </div>
  );
}
