import UserProfilePanel from "@/app/components/user-profile-panel";
import { apiFetch, requireCurrentUser } from "@/app/lib/server-api";

export default async function AdminUserProfilePage({ params, searchParams }) {
  const { userId } = await params;
  const resolvedSearchParams = await searchParams;
  const activityPage = Math.max(Number(resolvedSearchParams?.activity_page || "1") || 1, 1);
  const currentUser = await requireCurrentUser();
  const response = await apiFetch(`/api/admin/users/${userId}?activity_page=${activityPage}`);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load user profile.");
  }

  return (
    <UserProfilePanel
      user={payload.user}
      tokens={payload.tokens}
      permissions={payload.permissions}
      recentActivity={payload.recent_activity}
      activityPagination={payload.activity_pagination}
      currentUserId={currentUser?.id ?? null}
    />
  );
}
