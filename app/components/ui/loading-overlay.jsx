export default function LoadingOverlay({ message = "Waiting for API response..." }) {
  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 px-6 text-slate-100 backdrop-blur-[1px]"
      role="status"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="flex min-w-64 flex-col items-center rounded-2xl border border-cyan-200/20 bg-slate-950/90 px-8 py-7 text-center shadow-2xl shadow-slate-950/60">
        <span
          aria-hidden="true"
          className="h-12 w-12 animate-spin rounded-full border-4 border-cyan-200/30 border-t-cyan-200"
        />
        <p className="mt-5 text-sm font-semibold uppercase tracking-[0.22em] text-cyan-200">Loading</p>
        <p className="mt-2 text-sm text-slate-300">{message}</p>
      </div>
    </div>
  );
}
