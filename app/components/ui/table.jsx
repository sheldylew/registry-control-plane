export function TableShell({ children }) {
  return (
    <div className="overflow-hidden rounded-lg border border-white/10">
      <div className="overflow-x-auto">{children}</div>
    </div>
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
