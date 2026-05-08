import RobotsPanel from "@/app/components/robots-panel";
import { apiFetch } from "@/app/lib/server-api";

export default async function AdminRobotsPage() {
  const response = await apiFetch("/api/admin/robots");
  const payload = await response.json();

  return <RobotsPanel initialRobots={payload.robots} />;
}
