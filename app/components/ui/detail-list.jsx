export default function DetailList({ items, columns = 2, compact = false }) {
  return (
    <dl className={`grid gap-4 ${columns === 1 ? "grid-cols-1" : "md:grid-cols-2"}`}>
      {items.map((item) => (
        <div
          key={item.label}
          className={`rounded-lg border border-white/10 bg-slate-950/60 ${compact ? "px-4 py-3" : "px-4 py-4"}`}
        >
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{item.label}</dt>
          <dd className="mt-2 break-words text-sm text-slate-200">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
