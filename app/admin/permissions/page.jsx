import PermissionsPanel from "@/app/components/permissions-panel";
import { apiFetch } from "@/app/lib/server-api";

function buildApiPath(page) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  return `/api/admin/permissions?${params.toString()}`;
}

export default async function AdminPermissionsPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(buildApiPath(page));
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load permissions.");
  }

  return (
    <PermissionsPanel
      initialUsers={payload.users}
      initialRobots={payload.robots}
      initialPermissions={payload.permissions}
      pagination={payload.pagination}
    />
  );
}
