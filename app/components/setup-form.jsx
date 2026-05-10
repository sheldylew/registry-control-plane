"use client";

import { useState } from "react";

import Alert from "@/app/components/ui/alert";
import Button from "@/app/components/ui/button";
import { Field, Input, LightInput } from "@/app/components/ui/form";
import { Panel } from "@/app/components/ui/panel";
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
    <Panel as="form" onSubmit={onSubmit} className="p-8 shadow-2xl shadow-slate-950/30">
      <h1 className="text-3xl font-semibold text-white">First boot setup</h1>
      <p className="mt-3 text-sm leading-6 text-slate-300">
        Enter the one-time setup token from container logs, then create the first admin account and public registry origin.
      </p>

      {!result ? (
        <>
          <Field label="Setup token" className="mt-6">
            <Input
              value={setupToken}
              onChange={(event) => setSetupToken(event.target.value)}
              required
              autoComplete="one-time-code"
            />
          </Field>

          <Field label="Admin username" className="mt-5">
            <Input
              value={adminUsername}
              onChange={(event) => setAdminUsername(event.target.value)}
              required
              maxLength={255}
              autoComplete="username"
            />
          </Field>

          <Field label="Admin email" className="mt-5">
            <Input
              value={adminEmail}
              onChange={(event) => setAdminEmail(event.target.value)}
              required
              maxLength={320}
              type="email"
              autoComplete="email"
            />
          </Field>

          <Field label="Admin password" className="mt-5">
            <LightInput
              value={adminPassword}
              onChange={(event) => setAdminPassword(event.target.value)}
              required
              minLength={8}
              type="password"
              autoComplete="new-password"
            />
          </Field>

          <Field label="Public registry origin" className="mt-5">
            <Input
              value={publicOrigin}
              onChange={(event) => setPublicOrigin(event.target.value)}
              required
              maxLength={255}
              placeholder="https://registry.example.com"
            />
          </Field>
        </>
      ) : null}

      {error ? (
        <Alert tone="rose" className="mt-4">{error}</Alert>
      ) : null}

      {result ? (
        <Alert tone="amber" className="mt-4">
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
        </Alert>
      ) : null}

      {!result ? (
        <Button
          type="submit"
          disabled={pending || !canSubmit}
          loading={pending}
          className="mt-6 w-full"
          size="lg"
        >
          {pending ? "Completing setup..." : "Complete setup"}
        </Button>
      ) : null}
    </Panel>
  );
}
