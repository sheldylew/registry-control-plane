import RepositoriesPanel from "@/app/components/repositories-panel";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { apiFetch } from "@/app/lib/server-api";
import { getUiTimezone } from "@/app/lib/ui-settings";

function buildApiPath(page, sort, direction) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  if (sort !== "updated" || direction !== "desc") {
    params.set("sort", sort);
    params.set("direction", direction);
  }
  return `/api/repos?${params.toString()}`;
}

export default async function ReposPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const timeZone = await getUiTimezone();
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const sort = ["updated", "name"].includes(resolvedSearchParams?.sort) ? resolvedSearchParams.sort : "updated";
  const direction = ["asc", "desc"].includes(resolvedSearchParams?.direction) ? resolvedSearchParams.direction : "desc";
  const response = await apiFetch(buildApiPath(page, sort, direction));
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

      <RepositoriesPanel initialPayload={payload} timeZone={timeZone} />
    </div>
  );
}
