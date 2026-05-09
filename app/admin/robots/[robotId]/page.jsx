import RobotProfilePanel from "@/app/components/robot-profile-panel";
import { apiFetch } from "@/app/lib/server-api";

export default async function AdminRobotProfilePage({ params }) {
  const { robotId } = await params;
  const response = await apiFetch(`/api/admin/robots/${robotId}`);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load robot profile.");
  }

  return (
    <RobotProfilePanel
      robot={payload.robot}
      permissions={payload.permissions}
      recentActivity={payload.recent_activity}
    />
  );
}
