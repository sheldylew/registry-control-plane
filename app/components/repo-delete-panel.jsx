"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { TrashIcon } from "@heroicons/react/24/outline";

import Button from "@/app/components/ui/button";
import Dialog from "@/app/components/ui/dialog";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function RepoDeletePanel({
  title,
  description,
  warning,
  confirmationLabel,
  confirmationValue,
  requireConfirmation = true,
  endpoint,
  buttonLabel,
  successLabel,
  redirectPath = "/repos",
  compact = false,
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const canSubmit = requireConfirmation ? confirmation === confirmationValue : true;

  function openDialog() {
    setConfirmation("");
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
    setPending(true);
    setError("");

    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({ confirmation: requireConfirmation ? confirmation : confirmationValue }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Delete failed.");
      setPending(false);
      return;
    }

    setConfirmation("");
    setOpen(false);
    router.push(redirectPath);
    router.refresh();
    setPending(false);
  }

  const triggerClassName = compact
    ? "h-10 w-10"
    : "h-11 w-11";

  const triggerButton = (
    <Button
      type="button"
      onClick={openDialog}
      variant="danger"
      size={compact ? "iconMd" : "iconLg"}
      className={triggerClassName}
      aria-label={title}
      title={title}
    >
      <TrashIcon className="h-5 w-5" aria-hidden="true" />
    </Button>
  );

  return (
    <>
      {compact ? null : (
        <div className="rounded-lg border border-rose-400/20 bg-rose-500/5 p-4 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-rose-200">
              {title}
            </p>
            {triggerButton}
          </div>
          <p className="mt-3 text-sm leading-7 text-slate-300">{description}</p>
        </div>
      )}

      {compact ? triggerButton : null}

      <Dialog open={open} onClose={closeDialog} eyebrow="Confirm delete" title={title}>
        <p className="text-sm leading-7 text-slate-300">{description}</p>
        {warning ? (
          <div className="mt-4 rounded-lg border border-amber-300/30 bg-amber-300/10 p-4 text-sm leading-7 text-amber-100">
            {warning}
          </div>
        ) : null}
        {requireConfirmation ? (
          <>
            <p className="mt-5 text-xs uppercase tracking-[0.18em] text-slate-400">
              {confirmationLabel}
            </p>
            <p className="mt-2 break-all rounded-lg border border-white/10 bg-slate-950/70 px-4 py-3 font-mono text-xs text-white">
              {confirmationValue}
            </p>
          </>
        ) : null}

        <form onSubmit={onSubmit} className="mt-4">
          {requireConfirmation ? (
            <input
              autoFocus
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={confirmationValue}
              required
              className="w-full rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-white outline-none focus:border-rose-300/50"
            />
          ) : null}
          {error ? (
            <p className="mt-3 text-sm text-rose-200">{error}</p>
          ) : null}
          <div className="mt-5 grid gap-3 sm:flex sm:items-center sm:justify-end">
            <Button
              type="button"
              onClick={closeDialog}
              disabled={pending}
              variant="secondary"
              className="w-full sm:w-auto"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={pending || !canSubmit}
              loading={pending}
              variant="danger"
              className="w-full sm:w-auto"
            >
              {pending ? successLabel : buttonLabel}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
