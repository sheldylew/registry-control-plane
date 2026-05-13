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
      {action ? <div className="w-full shrink-0 sm:w-auto">{action}</div> : null}
    </div>
  );
}

export function MobileCollapsiblePanel({
  as: Component = "section",
  id,
  className = "",
  eyebrow,
  title,
  summaryMeta,
  openLabel = "Open details",
  hideLabel = "Hide details",
  children,
}) {
  return (
    <>
      <details
        id={id}
        className={`group rounded-lg border border-white/10 bg-slate-900/80 p-4 shadow-sm shadow-slate-950/20 lg:hidden ${className}`}
      >
        <summary className="cursor-pointer list-none marker:hidden">
          {eyebrow ? (
            <span className="block text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
              {eyebrow}
            </span>
          ) : null}
          <span className={eyebrow ? "mt-2 block text-lg font-semibold text-white" : "block text-lg font-semibold text-white"}>
            {title}
          </span>
          {summaryMeta ? <span className="mt-2 block text-sm leading-6 text-slate-300">{summaryMeta}</span> : null}
          <span className="mt-3 inline-flex text-sm font-medium text-cyan-200 group-open:hidden">{openLabel}</span>
          <span className="mt-3 hidden text-sm font-medium text-cyan-200 group-open:inline-flex">{hideLabel}</span>
        </summary>
        <div className="mt-4 border-t border-white/10 pt-4">{children}</div>
      </details>
      <Panel as={Component} id={id ? `${id}-desktop` : undefined} className={`hidden lg:block ${className}`}>
        {children}
      </Panel>
    </>
  );
}
