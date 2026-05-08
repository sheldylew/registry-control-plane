export function Panel({ as: Component = "section", className = "", children, ...props }) {
  return (
    <Component
      className={`rounded-lg border border-white/10 bg-slate-900/80 shadow-sm shadow-slate-950/20 ${className}`}
      {...props}
    >
      {children}
    </Component>
  );
}

export function PanelHeader({ eyebrow, title, description, action, className = "" }) {
  return (
    <div className={`flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between ${className}`}>
      <div>
        {eyebrow ? (
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            {eyebrow}
          </p>
        ) : null}
        <h2 className={eyebrow ? "mt-2 text-xl font-semibold text-white" : "text-xl font-semibold text-white"}>
          {title}
        </h2>
        {description ? <p className="mt-2 text-sm leading-6 text-slate-300">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
