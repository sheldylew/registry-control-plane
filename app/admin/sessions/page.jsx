import SessionsPanel from "@/app/components/sessions-panel";
import { apiFetch } from "@/app/lib/server-api";
import { getUiTimezone } from "@/app/lib/ui-settings";

function buildApiPath(page, pageSize) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return `/api/admin/sessions?${params.toString()}`;
}

export default async function AdminSessionsPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const timeZone = await getUiTimezone();
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const pageSize = Math.min(Math.max(Number(resolvedSearchParams?.page_size || "10") || 10, 1), 100);
  const response = await apiFetch(buildApiPath(page, pageSize));
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.detail || "Failed to load sessions.");
  }

  return (
    <SessionsPanel
      initialSessions={payload.sessions}
      summary={payload.summary}
      pagination={payload.pagination}
      timeZone={timeZone}
    />
  );
}
