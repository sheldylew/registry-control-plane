import UsersPanel from "@/app/components/users-panel";
import { apiFetch, requireCurrentUser } from "@/app/lib/server-api";

function buildApiPath(page) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  return `/api/admin/users?${params.toString()}`;
}

export default async function AdminUsersPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const currentUser = await requireCurrentUser();
  const response = await apiFetch(buildApiPath(page));
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load users.");
  }

  return (
    <UsersPanel
      initialUsers={payload.users}
      currentUserId={currentUser?.id ?? null}
      pagination={payload.pagination}
    />
  );
}
