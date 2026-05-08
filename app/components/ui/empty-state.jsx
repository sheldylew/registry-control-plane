export default function EmptyState({ title, description, action }) {
  return (
    <div className="rounded-lg border border-dashed border-white/15 bg-slate-950/40 px-6 py-10 text-center">
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      {description ? <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-400">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
