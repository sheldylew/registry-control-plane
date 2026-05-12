export default function StatCard({ label, value, detail, tone = "slate", badge = null, badgeTone = "amber" }) {
  const tones = {
    slate: "border-white/10 bg-slate-900/80",
    cyan: "border-cyan-300/20 bg-cyan-400/10",
    emerald: "border-emerald-300/20 bg-emerald-400/10",
    amber: "border-amber-300/20 bg-amber-400/10",
  };
  const badgeTones = {
    amber: "border-amber-300/30 bg-amber-400/10 text-amber-100",
    emerald: "border-emerald-300/30 bg-emerald-400/10 text-emerald-100",
    slate: "border-white/10 bg-white/5 text-slate-300",
  };

  return (
    <article className={`rounded-lg border p-6 shadow-sm shadow-slate-950/20 ${tones[tone]}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-slate-300">{label}</p>
        {badge ? (
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-[0.14em] ${
              badgeTones[badgeTone] || badgeTones.amber
            }`}
          >
            {badge}
          </span>
        ) : null}
      </div>
      <p className="mt-4 text-2xl font-semibold leading-tight text-white sm:text-3xl">{value}</p>
      {detail ? <p className="mt-2 text-sm text-slate-400">{detail}</p> : null}
    </article>
  );
}
