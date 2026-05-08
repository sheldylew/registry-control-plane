const tones = {
  slate: "bg-white/5 text-slate-300 ring-white/10",
  cyan: "bg-cyan-400/10 text-cyan-100 ring-cyan-300/30",
  emerald: "bg-emerald-400/10 text-emerald-100 ring-emerald-300/30",
  amber: "bg-amber-400/10 text-amber-100 ring-amber-300/30",
  rose: "bg-rose-400/10 text-rose-100 ring-rose-300/30",
};

export default function Badge({ tone = "slate", dot = false, children }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}
    >
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
