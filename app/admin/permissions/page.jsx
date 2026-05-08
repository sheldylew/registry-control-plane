import PermissionsPanel from "@/app/components/permissions-panel";
import { apiFetch } from "@/app/lib/server-api";

export default async function AdminPermissionsPage() {
  const response = await apiFetch("/api/admin/permissions");
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load permissions.");
  }

  return (
    <PermissionsPanel
      initialUsers={payload.users}
      initialRobots={payload.robots}
      initialPermissions={payload.permissions}
    />
  );
}
