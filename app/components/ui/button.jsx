const baseButtonClasses =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60";

const variants = {
  primary: "bg-cyan-400 text-slate-950 hover:bg-cyan-300 focus-visible:outline-cyan-300",
  secondary:
    "border border-white/10 bg-white/5 text-slate-100 hover:border-white/20 hover:bg-white/10 focus-visible:outline-slate-400",
  soft: "border border-cyan-300/20 bg-cyan-400/10 text-cyan-100 hover:bg-cyan-400/20 focus-visible:outline-cyan-300",
  warning:
    "border border-amber-300/30 bg-amber-400/10 text-amber-100 hover:bg-amber-400/20 focus-visible:outline-amber-300",
  danger:
    "border border-rose-300/30 bg-rose-400/15 text-rose-100 hover:bg-rose-400/25 focus-visible:outline-rose-300",
  ghost: "text-slate-300 hover:bg-white/5 hover:text-white focus-visible:outline-slate-400",
};

const sizes = {
  xs: "h-8 px-2.5 py-1 text-xs",
  sm: "h-9 px-3 py-1.5",
  md: "h-10 px-4 py-2",
  lg: "h-11 px-4 py-2.5",
  iconSm: "h-8 w-8 p-0",
  iconMd: "h-10 w-10 p-0",
  iconLg: "h-11 w-11 p-0",
};

export function buttonClassName({ variant = "primary", size = "md", className = "" } = {}) {
  return [baseButtonClasses, variants[variant], sizes[size], className].filter(Boolean).join(" ");
}

export default function Button({
  as: Component = "button",
  variant = "primary",
  size = "md",
  className = "",
  ...props
}) {
  return (
    <Component
      className={buttonClassName({ variant, size, className })}
      {...props}
    />
  );
}
