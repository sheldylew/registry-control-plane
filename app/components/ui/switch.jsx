"use client";

export default function Switch({
  checked,
  onChange,
  disabled = false,
  label,
  description,
  srLabel,
  align = "center",
}) {
  const toggleLabel = srLabel || label || "Toggle";

  return (
    <div className={`flex gap-3 ${align === "start" ? "items-start" : "items-center"} ${disabled ? "opacity-60" : ""}`}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={toggleLabel}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 ${
          checked
            ? "border-cyan-300/50 bg-cyan-400/80"
            : "border-white/10 bg-slate-800"
        }`}
      >
        <span
          aria-hidden="true"
          className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-slate-950 transition-transform ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
      {label || description ? (
        <div>
          {label ? <p className="text-sm font-medium text-white">{label}</p> : null}
          {description ? <p className="text-sm text-slate-400">{description}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
