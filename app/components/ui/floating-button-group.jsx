export default function FloatingButtonGroup({ items, className = "" }) {
  return (
    <nav className={`sticky top-3 z-20 flex justify-center lg:hidden ${className}`} aria-label="Section navigation">
      <div className="inline-flex max-w-full overflow-x-auto rounded-full border border-white/10 bg-slate-950/80 p-1 shadow-2xl shadow-cyan-950/30 ring-1 ring-cyan-300/10 backdrop-blur-xl">
        {items.map((item, index) => (
          <a
            key={item.href}
            href={item.href}
            className={`shrink-0 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:bg-white/10 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 ${
              index === 0 ? "rounded-l-full" : ""
            } ${index === items.length - 1 ? "rounded-r-full" : ""}`}
          >
            {item.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
