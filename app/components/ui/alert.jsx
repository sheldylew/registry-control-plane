const tones = {
  rose: "border-rose-400/30 bg-rose-400/10 text-rose-100",
  amber: "border-amber-300/30 bg-amber-300/10 text-amber-100",
  emerald: "border-emerald-400/30 bg-emerald-400/10 text-emerald-100",
  slate: "border-white/10 bg-white/5 text-slate-200",
};

export default function Alert({ tone = "slate", children, className = "" }) {
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${tones[tone]} ${className}`}>
      {children}
    </div>
  );
}
