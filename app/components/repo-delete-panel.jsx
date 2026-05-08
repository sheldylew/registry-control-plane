"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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
    ? "inline-flex h-8 w-8 items-center justify-center rounded-full border border-rose-300/25 bg-rose-400/10 text-rose-100 transition hover:bg-rose-400/20"
    : "inline-flex h-11 w-11 items-center justify-center rounded-full border border-rose-300/30 bg-rose-400/15 text-rose-100 transition hover:bg-rose-400/25";

  const triggerButton = (
    <button
      type="button"
      onClick={openDialog}
      className={triggerClassName}
      aria-label={title}
      title={title}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className={compact ? "h-4 w-4" : "h-5 w-5"}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3 6h18" />
        <path d="M8 6V4.5A1.5 1.5 0 0 1 9.5 3h5A1.5 1.5 0 0 1 16 4.5V6" />
        <path d="M6.5 6l1 13a2 2 0 0 0 2 1.8h5a2 2 0 0 0 2-1.8l1-13" />
        <path d="M10 10.5v6" />
        <path d="M14 10.5v6" />
      </svg>
    </button>
  );

  return (
    <>
      {compact ? null : (
        <div className="rounded-3xl border border-rose-400/20 bg-rose-500/5 p-6">
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
        {requireConfirmation ? (
          <>
            <p className="mt-5 text-xs uppercase tracking-[0.18em] text-slate-400">
              {confirmationLabel}
            </p>
            <p className="mt-2 break-all rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 font-mono text-xs text-white">
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
              className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
            />
          ) : null}
          {error ? (
            <p className="mt-3 text-sm text-rose-200">{error}</p>
          ) : null}
          <div className="mt-5 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={closeDialog}
              disabled={pending}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-white/20 hover:text-white disabled:opacity-60"
            >
              Cancel
            </button>
              <button
                type="submit"
                disabled={pending || !canSubmit}
                className="rounded-full border border-rose-300/30 bg-rose-400/15 px-4 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-400/25 disabled:opacity-60"
              >
              {pending ? successLabel : buttonLabel}
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
