export function Field({ label, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="text-sm font-medium text-slate-200">{label}</span>
      <span className="mt-2 block">{children}</span>
    </label>
  );
}

export function Input({ className = "", ...props }) {
  return (
    <input
      className={`w-full rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-300/50 focus:ring-2 focus:ring-cyan-300/10 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...props}
    />
  );
}

export function LightInput({ className = "", ...props }) {
  return (
    <input
      className={`w-full rounded-md border border-white/10 bg-slate-100 px-3 py-2 text-slate-950 outline-none transition placeholder:text-slate-500 focus:border-cyan-300/50 focus:ring-2 focus:ring-cyan-300/10 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      {...props}
    />
  );
}

export function CheckboxField({ label, checked, onChange, id }) {
  return (
    <label className="flex items-center gap-3 rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-200">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-white/10 bg-white/5 text-cyan-400 focus:ring-cyan-300/30"
      />
      {label}
    </label>
  );
}
