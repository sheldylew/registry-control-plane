export default function StatCard({ label, value, detail, tone = "slate" }) {
  const tones = {
    slate: "border-white/10 bg-slate-900/80",
    cyan: "border-cyan-300/20 bg-cyan-400/10",
    emerald: "border-emerald-300/20 bg-emerald-400/10",
    amber: "border-amber-300/20 bg-amber-400/10",
  };

  return (
    <article className={`rounded-lg border p-6 shadow-sm shadow-slate-950/20 ${tones[tone]}`}>
      <p className="text-sm font-medium text-slate-300">{label}</p>
      <p className="mt-4 text-3xl font-semibold text-white">{value}</p>
      {detail ? <p className="mt-2 text-sm text-slate-400">{detail}</p> : null}
    </article>
  );
}
