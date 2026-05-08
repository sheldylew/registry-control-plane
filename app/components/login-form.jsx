"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { EyeIcon, EyeSlashIcon } from "@heroicons/react/24/outline";

import Alert from "@/app/components/ui/alert";
import Button from "@/app/components/ui/button";
import { Field, Input, LightInput } from "@/app/components/ui/form";
import { Panel } from "@/app/components/ui/panel";
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
    <Panel as="form" onSubmit={onSubmit} className="p-8 shadow-2xl shadow-slate-950/30">
      <h1 className="text-3xl font-semibold text-white">Sign in</h1>
      <p className="mt-3 text-sm leading-6 text-slate-300">
        Use an admin account to manage users, access tokens, and robots.
      </p>

      <Field label="Username" className="mt-6">
        <Input
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
          maxLength={255}
          autoComplete="username"
        />
      </Field>

      <Field label="Password" className="mt-5">
        <div className="relative">
          <LightInput
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            className="pr-12"
            autoComplete="current-password"
          />
        <Button
          type="button"
          onClick={() => setShowPassword((current) => !current)}
          variant="ghost"
          size="iconMd"
          className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:bg-slate-200 hover:text-slate-900"
          aria-label={showPassword ? "Hide password" : "Show password"}
          aria-pressed={showPassword}
        >
          {showPassword ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
        </Button>
        </div>
      </Field>

      {error ? (
        <Alert tone="rose" className="mt-4">{error}</Alert>
      ) : null}

      <Button
        type="submit"
        disabled={pending || !canSubmit}
        className="mt-6 w-full"
        size="lg"
      >
        {pending ? "Signing in..." : "Sign in"}
      </Button>
    </Panel>
  );
}
