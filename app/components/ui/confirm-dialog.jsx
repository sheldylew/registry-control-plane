"use client";

import { useState } from "react";

import Alert from "@/app/components/ui/alert";
import Button from "@/app/components/ui/button";
import Dialog from "@/app/components/ui/dialog";

export default function ConfirmDialog({
  open,
  onClose,
  title,
  eyebrow = "Confirm action",
  description,
  confirmationLabel,
  confirmationValue,
  onConfirm,
  confirmLabel = "Confirm",
  pendingLabel = "Working...",
}) {
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const requiresConfirmation = Boolean(confirmationValue);
  const canConfirm = requiresConfirmation ? confirmation === confirmationValue : true;

  async function submit(event) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await onConfirm(confirmation);
      setConfirmation("");
      onClose();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Action failed.");
    } finally {
      setPending(false);
    }
  }

  function handleClose() {
    if (pending) {
      return;
    }
    setConfirmation("");
    setError("");
    onClose();
  }

  return (
    <Dialog open={open} onClose={handleClose} eyebrow={eyebrow} title={title}>
      <p className="text-sm leading-7 text-slate-300">{description}</p>
      <form onSubmit={submit} className="mt-4">
        {requiresConfirmation ? (
          <>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">{confirmationLabel}</p>
            <p className="mt-2 break-all rounded-lg border border-white/10 bg-slate-950/70 px-4 py-3 font-mono text-xs text-white">
              {confirmationValue}
            </p>
            <input
              autoFocus
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={confirmationValue}
              className="mt-4 w-full rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-white outline-none focus:border-rose-300/50"
            />
          </>
        ) : null}
        {error ? <Alert tone="rose" className="mt-4">{error}</Alert> : null}
        <div className="mt-5 flex items-center justify-end gap-3">
          <Button type="button" onClick={handleClose} disabled={pending} variant="secondary">
            Cancel
          </Button>
          <Button type="submit" disabled={pending || !canConfirm} loading={pending} variant="danger">
            {pending ? pendingLabel : confirmLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
