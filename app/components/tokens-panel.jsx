"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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
      <form
        onSubmit={createToken}
        className="rounded-3xl border border-white/10 bg-slate-900/80 p-6"
      >
        <h2 className="text-xl font-semibold text-white">Personal access tokens</h2>
        <p className="mt-3 text-sm text-slate-300">
          Create a token for Docker CLI access. The raw secret is shown once.
        </p>
        <div className="mt-4 flex gap-3">
          <input
            placeholder="Token name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={FORM_NAME_MAX_LENGTH}
            className="flex-1 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
          />
          <button
            disabled={!canCreateToken}
            className="rounded-xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Create token
          </button>
        </div>
        {latestToken ? (
          <div className="mt-4 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-emerald-200">
              Copy now
            </p>
            <p className="mt-2 break-all font-mono text-sm text-white">{latestToken}</p>
          </div>
        ) : null}
        {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}
      </form>

      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <h2 className="text-xl font-semibold text-white">Issued tokens</h2>
        <ul className="mt-4 space-y-3">
          {initialTokens.map((token) => (
            <li
              key={token.id}
              className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 md:flex-row md:items-center md:justify-between"
            >
              <div>
                <p className="text-sm font-semibold text-white">{token.name}</p>
                <p className="mt-1 font-mono text-xs text-slate-400">
                  prefix: {token.token_prefix}
                </p>
              </div>
              {token.revoked_at ? (
                <span className="text-xs font-semibold text-amber-200">Revoked</span>
              ) : (
                <button
                  onClick={() => revokeToken(token.id)}
                  className="rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1 text-xs font-semibold text-amber-100"
                >
                  Revoke
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
