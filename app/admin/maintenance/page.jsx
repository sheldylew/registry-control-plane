import MaintenanceDashboardClient from "@/app/components/maintenance-dashboard-client";
import { getUiTimezone } from "@/app/lib/ui-settings";

export default async function AdminMaintenancePage({ searchParams }) {
  const [resolvedSearchParams, timeZone] = await Promise.all([
    searchParams,
    getUiTimezone(),
  ]);
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);

  return <MaintenanceDashboardClient key={page} initialPage={page} timeZone={timeZone} />;
}
