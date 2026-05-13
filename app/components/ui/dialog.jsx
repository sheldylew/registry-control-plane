"use client";

import { XMarkIcon } from "@heroicons/react/20/solid";

import Button from "@/app/components/ui/button";

export default function Dialog({
  open,
  onClose,
  eyebrow = "Dialog",
  title,
  children,
  panelClassName = "",
  maxWidth = "max-w-lg",
}) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 px-3 py-4 backdrop-blur-sm sm:px-4">
      <div className={`max-h-[calc(100vh-2rem)] w-full overflow-y-auto ${maxWidth} rounded-lg border border-white/10 bg-slate-900 p-4 shadow-2xl shadow-slate-950/40 sm:p-6 ${panelClassName}`}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-cyan-200">
              {eyebrow}
            </p>
            <h3 className="mt-2 text-xl font-semibold text-white sm:text-2xl">{title}</h3>
          </div>
          <Button
            type="button"
            onClick={onClose}
            variant="secondary"
            size="iconMd"
            aria-label="Close dialog"
          >
            <XMarkIcon className="h-5 w-5" aria-hidden="true" />
          </Button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}
