"use client";

import { useState } from "react";

import Alert from "@/app/components/ui/alert";
import Button from "@/app/components/ui/button";
import DetailList from "@/app/components/ui/detail-list";
import FormDialog from "@/app/components/ui/form-dialog";
import { Field, Input } from "@/app/components/ui/form";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { isValidPublicOrigin, normalizeTextInput, readApiErrorDetail } from "@/app/lib/user-form";

function readCookie(name) {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split("=")[1];
}

export default function SettingsPanel({ initialPublicOrigin, initialTimeZone, restartCommand }) {
  const [publicOrigin, setPublicOrigin] = useState(initialPublicOrigin || "");
  const [draftPublicOrigin, setDraftPublicOrigin] = useState(initialPublicOrigin || "");
  const [timeZone, setTimeZone] = useState(initialTimeZone || "America/Los_Angeles");
  const [draftTimeZone, setDraftTimeZone] = useState(initialTimeZone || "America/Los_Angeles");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [open, setOpen] = useState(false);
  const normalizedOrigin = normalizeTextInput(draftPublicOrigin).replace(/\/$/, "");
  const normalizedTimeZone = normalizeTextInput(draftTimeZone);
  const canSubmit = isValidPublicOrigin(normalizedOrigin) && Boolean(normalizedTimeZone);

  function openDialog() {
    setDraftPublicOrigin(publicOrigin);
    setDraftTimeZone(timeZone);
    setError("");
    setOpen(true);
  }

  function closeDialog() {
    if (pending) {
      return;
    }
    setOpen(false);
    setError("");
  }

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
      body: JSON.stringify({ public_registry_origin: normalizedOrigin, ui_timezone: normalizedTimeZone }),
    });
    const payload = await response.json().catch(() => ({}));
    setPending(false);

    if (!response.ok) {
      setError(readApiErrorDetail(payload, "Could not update settings."));
      return;
    }

    setPublicOrigin(payload.settings.public_registry_origin);
    setDraftPublicOrigin(payload.settings.public_registry_origin);
    setTimeZone(payload.settings.ui_timezone);
    setDraftTimeZone(payload.settings.ui_timezone);
    setMessage(payload.restart_command || "");
    setOpen(false);
  }

  return (
    <>
      <Panel className="p-6">
        <PanelHeader
          title="Registry origin"
          description="Review the public origin Docker clients use when the registry requests a bearer token."
          action={(
            <Button type="button" onClick={openDialog} size="lg">
              Edit origin
            </Button>
          )}
        />

        <div className="mt-6">
          <DetailList
            items={[
              {
                label: "Public origin",
                value: <code className="text-sm text-white">{publicOrigin || "Not configured"}</code>,
              },
              {
                label: "Registry restart",
                value: <code className="text-sm text-white">{restartCommand}</code>,
              },
              {
                label: "UI timezone",
                value: <code className="text-sm text-white">{timeZone}</code>,
              },
              {
                label: "Change behavior",
                value: "Origin changes require a registry restart. Timezone changes apply to the UI without restarting services.",
              },
            ]}
          />
        </div>

        {message ? (
          <Alert tone="amber" className="mt-6">
            <p>Registry restart required after the latest settings change.</p>
            <code className="mt-2 block rounded-lg bg-slate-950 px-3 py-2 text-amber-50">{message}</code>
          </Alert>
        ) : null}
      </Panel>

      <FormDialog
        open={open}
        onClose={closeDialog}
        eyebrow="Settings"
        title="Edit settings"
        description="Update the external registry origin used in bearer-token challenges and the timezone used for UI timestamps."
        onSubmit={onSubmit}
        submitLabel="Save settings"
        submitPendingLabel="Saving..."
        pending={pending}
        disabled={!canSubmit}
        error={error}
      >
        <Field label="Public registry origin">
          <Input
            autoFocus
            value={draftPublicOrigin}
            onChange={(event) => setDraftPublicOrigin(event.target.value)}
            required
            maxLength={255}
          />
        </Field>
        <Field label="UI timezone">
          <Input
            value={draftTimeZone}
            onChange={(event) => setDraftTimeZone(event.target.value)}
            required
            maxLength={128}
          />
        </Field>
      </FormDialog>
    </>
  );
}
