import TokensPanel from "@/app/components/tokens-panel";
import { apiFetch } from "@/app/lib/server-api";

export default async function AdminTokensPage() {
  const response = await apiFetch("/api/admin/tokens");
  const payload = await response.json();

  return <TokensPanel initialTokens={payload.tokens} />;
}
