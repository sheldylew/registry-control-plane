"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

const ToastContext = createContext(null);

const toneClasses = {
  success: "border-emerald-300/25 bg-emerald-400/10 text-emerald-50",
  error: "border-rose-300/25 bg-rose-400/10 text-rose-50",
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timeoutHandles = useRef(new Map());

  const dismissToast = useCallback((id) => {
    const handle = timeoutHandles.current.get(id);
    if (handle) {
      window.clearTimeout(handle);
      timeoutHandles.current.delete(id);
    }
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(({ title, description = "", tone = "success", duration = 3200 }) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setToasts((current) => [...current, { id, title, description, tone }]);
    const handle = window.setTimeout(() => dismissToast(id), duration);
    timeoutHandles.current.set(id, handle);
  }, [dismissToast]);

  const value = useMemo(() => ({ showToast, dismissToast }), [dismissToast, showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-full max-w-sm flex-col gap-3">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto rounded-xl border px-4 py-3 shadow-2xl backdrop-blur ${toneClasses[toast.tone] || toneClasses.success}`}
            role="status"
            aria-live="polite"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">{toast.title}</p>
                {toast.description ? (
                  <p className="mt-1 text-sm text-current/80">{toast.description}</p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => dismissToast(toast.id)}
                className="rounded-md px-2 py-1 text-xs text-current/70 transition hover:bg-white/10 hover:text-current"
                aria-label="Dismiss notification"
              >
                Close
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) {
    throw new Error("useToast must be used within ToastProvider.");
  }
  return value;
}
