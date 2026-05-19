export default function StatCard({
  label,
  value,
  detail,
  tone = "slate",
  badge = null,
  badgeTone = "amber",
  detailBadge = false,
  detailBadgeTone = "slate",
}) {
  const tones = {
    slate: "border-white/10 bg-slate-900/80",
    cyan: "border-cyan-300/20 bg-cyan-400/10",
    emerald: "border-emerald-300/20 bg-emerald-400/10",
    amber: "border-amber-300/20 bg-amber-400/10",
    sky: "border-sky-300/20 bg-sky-400/10",
  };
  const badgeTones = {
    amber: "border-amber-300/30 bg-amber-400/10 text-amber-100",
    cyan: "border-cyan-300/30 bg-cyan-400/10 text-cyan-100",
    emerald: "border-emerald-300/30 bg-emerald-400/10 text-emerald-100",
    slate: "border-white/10 bg-white/5 text-slate-300",
  };

  return (
    <article className={`min-w-0 rounded-lg border p-4 shadow-sm shadow-slate-950/20 sm:p-6 ${tones[tone]}`}>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <p className="min-w-0 text-xs font-medium uppercase tracking-[0.14em] text-slate-400 sm:text-sm sm:normal-case sm:tracking-normal sm:text-slate-300">{label}</p>
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
      <p className="mt-3 min-w-0 break-normal text-xl font-semibold leading-tight text-white sm:mt-4 2xl:text-2xl">{value}</p>
      {detail && detailBadge ? (
        <span
          className={`mt-3 inline-flex max-w-full rounded-full border px-2.5 py-1 text-xs font-semibold ${
            badgeTones[detailBadgeTone] || badgeTones.slate
          }`}
        >
          <span className="min-w-0 break-words">{detail}</span>
        </span>
      ) : null}
      {detail && !detailBadge ? <p className="mt-2 min-w-0 break-words text-xs leading-5 text-slate-400 sm:text-sm">{detail}</p> : null}
    </article>
  );
}
