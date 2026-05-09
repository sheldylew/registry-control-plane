import TokensPanel from "@/app/components/tokens-panel";
import { apiFetch } from "@/app/lib/server-api";

function buildApiPath(page) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  return `/api/admin/tokens?${params.toString()}`;
}

export default async function AdminTokensPage({ searchParams }) {
  const resolvedSearchParams = await searchParams;
  const page = Math.max(Number(resolvedSearchParams?.page || "1") || 1, 1);
  const response = await apiFetch(buildApiPath(page));
  const payload = await response.json();

  return <TokensPanel initialTokens={payload.tokens} pagination={payload.pagination} />;
}
