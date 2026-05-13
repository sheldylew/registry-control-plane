export function TableShell({ children, mobileCards = null }) {
  return (
    <>
      {mobileCards ? <div className="lg:hidden">{mobileCards}</div> : null}
      <div className={`${mobileCards ? "hidden lg:block" : ""} overflow-hidden rounded-lg border border-white/10`}>
        <div className="overflow-x-auto">{children}</div>
      </div>
    </>
  );
}

export function Table({ children }) {
  return <table className="min-w-full divide-y divide-white/10 text-left text-sm text-slate-200">{children}</table>;
}

export function TableHead({ children }) {
  return <thead className="bg-white/5 text-xs uppercase tracking-[0.16em] text-slate-400">{children}</thead>;
}

export function TableBody({ children }) {
  return <tbody className="divide-y divide-white/10">{children}</tbody>;
}

export function MobileCardList({ children }) {
  return <div className="space-y-3">{children}</div>;
}

export function MobileCard({ children, className = "" }) {
  return (
    <article className={`rounded-lg border border-white/10 bg-slate-950/60 p-4 shadow-sm shadow-slate-950/20 ${className}`}>
      {children}
    </article>
  );
}

export function MobileDisclosureCard({ summary, children, className = "" }) {
  return (
    <details className={`group rounded-lg border border-white/10 bg-slate-950/60 p-4 shadow-sm shadow-slate-950/20 ${className}`}>
      <summary className="cursor-pointer list-none marker:hidden">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">{summary}</div>
          <span className="shrink-0 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs font-medium text-cyan-100 group-open:hidden">
            Details
          </span>
          <span className="hidden shrink-0 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs font-medium text-cyan-100 group-open:inline-flex">
            Hide
          </span>
        </div>
      </summary>
      <div className="mt-4 border-t border-white/10 pt-4">{children}</div>
    </details>
  );
}

export function MobileField({ label, children, className = "" }) {
  return (
    <div className={className}>
      <dt className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-200">{children}</dd>
    </div>
  );
}
