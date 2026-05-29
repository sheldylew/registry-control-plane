export default function BrandMark({ className = "h-12 w-12", showText = false }) {
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <svg
        className={showText ? "h-full w-auto shrink-0" : "h-full w-full"}
        viewBox="0 0 256 256"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <rect width="256" height="256" rx="58" fill="#06101D" />
        <rect x="28" y="28" width="200" height="200" rx="46" fill="#06101D" stroke="#C8FF73" strokeWidth="7" />
        <path d="M128 55L192 92V166L128 203L64 166V92L128 55Z" fill="#32B846" />
        <path d="M128 55L192 92L128 129L64 92L128 55Z" fill="#D9FF94" fillOpacity="0.9" />
        <path d="M64 92L128 129V203L64 166V92Z" fill="#22A33B" />
        <path d="M192 92L128 129V203L192 166V92Z" fill="#15803D" />
        <path
          d="M128 55L192 92V166L128 203L64 166V92L128 55Z"
          stroke="#F7FFE7"
          strokeOpacity="0.62"
          strokeWidth="5"
          strokeLinejoin="round"
        />
        <path
          d="M142 118C142 110.268 135.732 104 128 104C120.268 104 114 110.268 114 118C114 122.496 116.12 126.513 119.417 129.073V134.302L112.681 154.255C111.889 156.602 113.635 159 116.111 159H139.889C142.365 159 144.111 156.602 143.319 154.255L136.583 134.302V129.073C139.88 126.513 142 122.496 142 118Z"
          fill="#06101D"
        />
      </svg>
      {showText ? (
        <span className="min-w-0 text-left">
          <span className="block text-sm font-semibold uppercase tracking-[0.28em] text-cyan-300">RCP</span>
          <span className="mt-1 block text-sm font-semibold leading-5 text-white">Registry Control Plane</span>
        </span>
      ) : null}
    </span>
  );
}
