"use client";

import Alert from "@/app/components/ui/alert";
import Button from "@/app/components/ui/button";
import Dialog from "@/app/components/ui/dialog";

export default function FormDialog({
  open,
  onClose,
  eyebrow,
  title,
  description,
  onSubmit,
  submitLabel,
  submitPendingLabel,
  pending = false,
  disabled = false,
  error = "",
  children,
  maxWidth,
}) {
  return (
    <Dialog open={open} onClose={onClose} eyebrow={eyebrow} title={title} maxWidth={maxWidth}>
      {description ? <p className="text-sm leading-7 text-slate-300">{description}</p> : null}
      <form onSubmit={onSubmit} className={description ? "mt-4" : ""}>
        <div className="grid gap-4">
          {children}
        </div>
        {error ? <Alert tone="rose" className="mt-4">{error}</Alert> : null}
        <div className="mt-5 flex items-center justify-end gap-3">
          <Button
            type="button"
            onClick={onClose}
            disabled={pending}
            variant="secondary"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={pending || disabled}
            loading={pending}
          >
            {pending ? submitPendingLabel : submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
