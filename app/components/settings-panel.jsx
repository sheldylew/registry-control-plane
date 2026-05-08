"use client";

import { useState } from "react";

import Alert from "@/app/components/ui/alert";
import Button from "@/app/components/ui/button";
import { Field, Input } from "@/app/components/ui/form";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
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
    <Panel as="form" onSubmit={onSubmit} className="p-6">
      <PanelHeader
        title="Registry origin"
        description="This is the external origin Docker clients use when the registry requests a bearer token."
      />
      <Field label="Public registry origin" className="mt-5">
        <Input
          value={publicOrigin}
          onChange={(event) => setPublicOrigin(event.target.value)}
          required
          maxLength={255}
        />
      </Field>

      {error ? (
        <Alert tone="rose" className="mt-4">{error}</Alert>
      ) : null}

      {message ? (
        <Alert tone="amber" className="mt-4">
          <p>Restart the registry service so Docker clients receive the updated token realm.</p>
          <code className="mt-2 block rounded-lg bg-slate-950 px-3 py-2 text-amber-50">{message}</code>
        </Alert>
      ) : null}

      <Button
        type="submit"
        disabled={pending || !canSubmit}
        className="mt-6"
        size="lg"
      >
        {pending ? "Saving..." : "Save settings"}
      </Button>
    </Panel>
  );
}
