import RepositoriesPanel from "@/app/components/repositories-panel";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { apiFetch } from "@/app/lib/server-api";

function buildApiPath(page) {
  return `/api/repos?page=${String(page)}`;
}

export default async function ReposPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(buildApiPath(page));
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

      <RepositoriesPanel initialPayload={payload} />
    </div>
  );
}
