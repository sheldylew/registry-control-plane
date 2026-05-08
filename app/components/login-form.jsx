"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { hasNonEmptyValue, isValidPassword, normalizeTextInput } from "@/app/lib/user-form";

export default function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const canSubmit = hasNonEmptyValue(username) && isValidPassword(password, 1);

  async function onSubmit(event) {
    event.preventDefault();
    const normalizedUsername = normalizeTextInput(username);
    if (!normalizedUsername) {
      setError("Username is required.");
      return;
    }
    if (!isValidPassword(password, 1)) {
      setError("Password is required.");
      return;
    }

    setPending(true);
    setError("");

    const response = await fetch("/api/session/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: normalizedUsername, password }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Login failed.");
      setPending(false);
      return;
    }

    router.push("/admin");
    router.refresh();
  }

  return (
    <form
      onSubmit={onSubmit}
      className="rounded-3xl border border-white/10 bg-slate-900/80 p-8 shadow-2xl shadow-slate-950/30"
    >
      <h1 className="text-3xl font-semibold text-white">Sign in</h1>
      <p className="mt-3 text-sm leading-6 text-slate-300">
        Use an admin account to manage users, access tokens, and robots.
      </p>

      <label className="mt-6 block text-sm font-medium text-slate-200">
        Username
      </label>
      <input
        value={username}
        onChange={(event) => setUsername(event.target.value)}
        required
        maxLength={255}
        className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-white outline-none ring-0"
        autoComplete="username"
      />

      <label className="mt-5 block text-sm font-medium text-slate-200">
        Password
      </label>
      <div className="relative mt-2">
        <input
          type={showPassword ? "text" : "password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          className="w-full rounded-xl border border-white/10 bg-slate-100 px-4 py-3 pr-14 text-slate-950 outline-none ring-0"
          autoComplete="current-password"
        />
        <button
          type="button"
          onClick={() => setShowPassword((current) => !current)}
          className="absolute right-2 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-200 hover:text-slate-900"
          aria-label={showPassword ? "Hide password" : "Show password"}
          aria-pressed={showPassword}
        >
          {showPassword ? (
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M3 3l18 18" />
              <path d="M10.6 10.7a3 3 0 0 0 4.2 4.2" />
              <path d="M9.9 4.2A10.9 10.9 0 0 1 12 4c5.3 0 9.3 4.2 10 8-.3 1.5-1.2 3-2.6 4.3" />
              <path d="M6.2 6.3C4.4 7.7 3.3 9.5 2 12c.7 3.8 4.7 8 10 8 1.8 0 3.4-.5 4.9-1.2" />
            </svg>
          ) : (
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M2 12s3.6-8 10-8 10 8 10 8-3.6 8-10 8-10-8-10-8Z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          )}
        </button>
      </div>

      {error ? (
        <p className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={pending || !canSubmit}
        className="mt-6 w-full rounded-xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Signing in..." : "Sign in"}
      </button>
    </form>
  );
}
