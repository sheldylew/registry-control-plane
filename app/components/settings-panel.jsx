"use client";

import { useState } from "react";

import { isValidPublicOrigin, normalizeTextInput, readApiErrorDetail } from "@/app/lib/user-form";

function readCookie(name) {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split("=")[1];
}

export default function SettingsPanel({ initialPublicOrigin, restartCommand }) {
  const [publicOrigin, setPublicOrigin] = useState(initialPublicOrigin || "");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const normalizedOrigin = normalizeTextInput(publicOrigin).replace(/\/$/, "");
  const canSubmit = isValidPublicOrigin(normalizedOrigin);

  async function onSubmit(event) {
    event.preventDefault();
    if (!canSubmit) {
      setError("Enter a valid public origin.");
      return;
    }

    setPending(true);
    setError("");
    setMessage("");
    const response = await fetch("/api/admin/settings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({ public_registry_origin: normalizedOrigin }),
    });
    const payload = await response.json().catch(() => ({}));
    setPending(false);

    if (!response.ok) {
      setError(readApiErrorDetail(payload, "Could not update settings."));
      return;
    }

    setPublicOrigin(payload.settings.public_registry_origin);
    setMessage(payload.restart_command || restartCommand);
  }

  return (
    <form onSubmit={onSubmit} className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
      <h2 className="text-xl font-semibold text-white">Registry origin</h2>
      <p className="mt-2 text-sm leading-6 text-slate-300">
        This is the external origin Docker clients use when the registry requests a bearer token.
      </p>
      <label className="mt-5 block text-sm font-medium text-slate-200">Public registry origin</label>
      <input
        value={publicOrigin}
        onChange={(event) => setPublicOrigin(event.target.value)}
        required
        maxLength={255}
        className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-0"
      />

      {error ? (
        <p className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </p>
      ) : null}

      {message ? (
        <div className="mt-4 rounded-xl border border-amber-300/30 bg-amber-300/10 px-4 py-3 text-sm text-amber-100">
          <p>Restart the registry service so Docker clients receive the updated token realm.</p>
          <code className="mt-2 block rounded-lg bg-slate-950 px-3 py-2 text-amber-50">{message}</code>
        </div>
      ) : null}

      <button
        type="submit"
        disabled={pending || !canSubmit}
        className="mt-6 rounded-xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Saving..." : "Save settings"}
      </button>
    </form>
  );
}
