"use client";

import { useState } from "react";

import {
  hasNonEmptyValue,
  isValidPassword,
  isValidPublicOrigin,
  isValidUserEmail,
  normalizeTextInput,
  readApiErrorDetail,
} from "@/app/lib/user-form";

export default function SetupForm({ initialPublicOrigin = "" }) {
  const [setupToken, setSetupToken] = useState("");
  const [adminUsername, setAdminUsername] = useState("admin");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [publicOrigin, setPublicOrigin] = useState(initialPublicOrigin);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [pending, setPending] = useState(false);

  const canSubmit =
    hasNonEmptyValue(setupToken) &&
    hasNonEmptyValue(adminUsername) &&
    isValidUserEmail(adminEmail) &&
    isValidPassword(adminPassword, 8) &&
    isValidPublicOrigin(normalizeTextInput(publicOrigin).replace(/\/$/, ""));

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    setResult(null);

    const normalizedOrigin = normalizeTextInput(publicOrigin).replace(/\/$/, "");
    if (!canSubmit) {
      setError("Complete every setup field with valid values.");
      return;
    }

    setPending(true);
    const response = await fetch("/api/setup/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        setup_token: normalizeTextInput(setupToken),
        admin_username: normalizeTextInput(adminUsername),
        admin_email: normalizeTextInput(adminEmail),
        admin_password: adminPassword,
        public_registry_origin: normalizedOrigin,
      }),
    });

    const payload = await response.json().catch(() => ({}));
    setPending(false);
    if (!response.ok) {
      setError(readApiErrorDetail(payload, "Setup failed."));
      return;
    }

    setResult(payload);
  }

  return (
    <form
      onSubmit={onSubmit}
      className="rounded-3xl border border-white/10 bg-slate-900/80 p-8 shadow-2xl shadow-slate-950/30"
    >
      <h1 className="text-3xl font-semibold text-white">First boot setup</h1>
      <p className="mt-3 text-sm leading-6 text-slate-300">
        Enter the one-time setup token from container logs, then create the first admin account and public registry origin.
      </p>

      {!result ? (
        <>
          <label className="mt-6 block text-sm font-medium text-slate-200">Setup token</label>
          <input
            value={setupToken}
            onChange={(event) => setSetupToken(event.target.value)}
            required
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-0"
            autoComplete="one-time-code"
          />

          <label className="mt-5 block text-sm font-medium text-slate-200">Admin username</label>
          <input
            value={adminUsername}
            onChange={(event) => setAdminUsername(event.target.value)}
            required
            maxLength={255}
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-0"
            autoComplete="username"
          />

          <label className="mt-5 block text-sm font-medium text-slate-200">Admin email</label>
          <input
            value={adminEmail}
            onChange={(event) => setAdminEmail(event.target.value)}
            required
            maxLength={320}
            type="email"
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-0"
            autoComplete="email"
          />

          <label className="mt-5 block text-sm font-medium text-slate-200">Admin password</label>
          <input
            value={adminPassword}
            onChange={(event) => setAdminPassword(event.target.value)}
            required
            minLength={8}
            type="password"
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-100 px-4 py-3 text-slate-950 outline-none ring-0"
            autoComplete="new-password"
          />

          <label className="mt-5 block text-sm font-medium text-slate-200">Public registry origin</label>
          <input
            value={publicOrigin}
            onChange={(event) => setPublicOrigin(event.target.value)}
            required
            maxLength={255}
            placeholder="https://registry.example.com"
            className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-0"
          />
        </>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="mt-4 rounded-xl border border-amber-300/30 bg-amber-300/10 px-4 py-3 text-sm text-amber-100">
          <p>
            Setup complete. Restart the registry service before signing in or using Docker clients so the running registry
            reloads the updated token realm.
          </p>
          <code className="mt-2 block rounded-lg bg-slate-950 px-3 py-2 text-amber-50">
            {result.restart_command || "docker compose restart registry"}
          </code>
          <a
            href="/login"
            className="mt-3 inline-block text-sm font-semibold text-amber-50 underline decoration-amber-200/50 underline-offset-4"
          >
            Continue to sign in after restart
          </a>
        </div>
      ) : null}

      {!result ? (
        <button
          type="submit"
          disabled={pending || !canSubmit}
          className="mt-6 w-full rounded-xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? "Completing setup..." : "Complete setup"}
        </button>
      ) : null}
    </form>
  );
}
