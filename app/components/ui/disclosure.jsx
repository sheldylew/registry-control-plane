"use client";

export default function Disclosure({
  titleClosed = "View",
  titleOpen = "Hide",
  meta,
  children,
  defaultOpen = false,
}) {
  return (
    <details
      defaultOpen={defaultOpen}
      className="group rounded-lg border border-white/10 bg-slate-950/70"
    >
      <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-200 marker:hidden">
        <span className="inline-flex items-center gap-2">
          <span className="group-open:hidden">{titleClosed}</span>
          <span className="hidden group-open:inline">{titleOpen}</span>
          {meta ? <span className="text-xs text-slate-400">{meta}</span> : null}
        </span>
      </summary>
      <div className="border-t border-white/10">{children}</div>
    </details>
  );
}
