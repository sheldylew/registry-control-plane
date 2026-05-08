"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { FORM_NAME_MAX_LENGTH, hasNonEmptyValue, normalizeTextInput, readApiErrorDetail } from "@/app/lib/user-form";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function TokensPanel({ initialTokens }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [latestToken, setLatestToken] = useState("");
  const [error, setError] = useState("");
  const canCreateToken = hasNonEmptyValue(name);

  async function createToken(event) {
    event.preventDefault();
    const normalizedName = normalizeTextInput(name);
    if (!normalizedName) {
      setError("Token name is required.");
      return;
    }

    setError("");
    const response = await fetch("/api/admin/tokens", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({ name: normalizedName }),
    });
    const payload = await response.json().catch(() => ({}));
    if (response.ok) {
      setLatestToken(payload.raw_token);
      setName("");
      router.refresh();
      return;
    }
    setError(readApiErrorDetail(payload, "Could not create token."));
  }

  async function revokeToken(tokenId) {
    await fetch(`/api/admin/tokens/${tokenId}/revoke`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    router.refresh();
  }

  return (
    <div className="space-y-6">
      <Panel as="form" onSubmit={createToken} className="p-6">
        <PanelHeader
          title="Personal access tokens"
          description="Create a token for Docker CLI access. The raw secret is shown once."
        />
        <div className="mt-4 flex gap-3">
          <input
            placeholder="Token name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={FORM_NAME_MAX_LENGTH}
            className="flex-1 rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-white outline-none focus:border-cyan-300/50"
          />
          <Button
            disabled={!canCreateToken}
            size="lg"
          >
            Create token
          </Button>
        </div>
        {latestToken ? (
          <div className="mt-4 rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-4">
            <Badge tone="emerald">Copy now</Badge>
            <p className="mt-2 break-all font-mono text-sm text-white">{latestToken}</p>
          </div>
        ) : null}
        {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}
      </Panel>

      <Panel className="p-6">
        <PanelHeader title="Issued tokens" description="Review active and revoked personal access tokens." />
        <ul className="mt-4 space-y-3">
          {initialTokens.length ? initialTokens.map((token) => (
            <li
              key={token.id}
              className="flex flex-col gap-3 rounded-lg border border-white/10 bg-slate-950/60 px-4 py-4 md:flex-row md:items-center md:justify-between"
            >
              <div>
                <p className="text-sm font-semibold text-white">{token.name}</p>
                <p className="mt-1 font-mono text-xs text-slate-400">
                  prefix: {token.token_prefix}
                </p>
              </div>
              {token.revoked_at ? (
                <Badge tone="amber" dot>
                  Revoked
                </Badge>
              ) : (
                <Button
                  type="button"
                  onClick={() => revokeToken(token.id)}
                  variant="warning"
                  size="xs"
                >
                  Revoke
                </Button>
              )}
            </li>
          )) : null}
        </ul>
        {!initialTokens.length ? (
          <div className="mt-6">
            <EmptyState
              title="No issued tokens"
              description="Create a token when an operator needs Docker CLI access."
            />
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
