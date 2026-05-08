import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import { Panel } from "@/app/components/ui/panel";

const apiBasePath = process.env.NEXT_PUBLIC_API_BASE_PATH || "/api";
const authTokenPath = process.env.NEXT_PUBLIC_AUTH_TOKEN_PATH || "/auth/token";
const registryBasePath =
  process.env.NEXT_PUBLIC_REGISTRY_BASE_PATH || "/v2/";

export const revalidate = 86400;

const productionSignals = [
  "Bootstrap an admin account, sign in from the browser, and manage access without hand-editing registry config",
  "Issue scoped bearer tokens, PATs, and robot credentials for laptops, build agents, and homelab automation",
  "Run on a pinned Docker Compose stack with health checks, upgrade scripts, and registry maintenance controls",
];

const operatorWorkflows = [
  "Keep a small team or single maintainer setup organized with repository-level permissions and audit history",
  "Browse repositories, inspect tags, and review manifest details without dropping into raw registry APIs first",
  "Treat the registry like production infrastructure even when it lives in a closet rack, spare mini PC, or NAS",
];

export default function HomePage() {
  const currentYear = new Date().getFullYear();

  return (
    <main className="relative mx-auto flex min-h-screen max-w-7xl flex-col overflow-hidden px-6 py-10 lg:px-8">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -bottom-20 -right-16 h-[30rem] w-[48rem] rounded-full bg-[radial-gradient(circle,_rgba(34,211,238,0.16),_transparent_66%)]" />
        <svg
          className="absolute -bottom-12 -right-20 h-[30rem] w-[46rem] opacity-70"
          viewBox="0 0 640 420"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <g opacity="0.9">
            <rect x="32" y="36" width="86" height="86" rx="18" stroke="#94A3B8" strokeOpacity="0.22" strokeWidth="2" />
            <rect x="72" y="78" width="154" height="154" rx="24" stroke="#22D3EE" strokeOpacity="0.2" strokeWidth="2" />
            <rect x="188" y="18" width="116" height="116" rx="22" stroke="#CBD5E1" strokeOpacity="0.16" strokeWidth="2" />
            <rect x="248" y="92" width="208" height="208" rx="28" stroke="#34D399" strokeOpacity="0.18" strokeWidth="2" />
            <rect x="428" y="38" width="92" height="92" rx="18" stroke="#E2E8F0" strokeOpacity="0.14" strokeWidth="2" />
            <rect x="486" y="128" width="122" height="122" rx="20" stroke="#22D3EE" strokeOpacity="0.14" strokeWidth="2" />
            <path d="M56 284H214" stroke="#94A3B8" strokeOpacity="0.16" strokeWidth="2" />
            <path d="M92 320H332" stroke="#CBD5E1" strokeOpacity="0.14" strokeWidth="2" />
            <path d="M168 360H472" stroke="#34D399" strokeOpacity="0.14" strokeWidth="2" />
            <circle cx="122" cy="176" r="8" fill="#22D3EE" fillOpacity="0.24" />
            <circle cx="340" cy="64" r="6" fill="#E2E8F0" fillOpacity="0.2" />
            <circle cx="400" cy="312" r="10" fill="#34D399" fillOpacity="0.16" />
            <circle cx="540" cy="102" r="7" fill="#22D3EE" fillOpacity="0.18" />
          </g>
        </svg>
        <div className="absolute -bottom-8 -right-8 h-[28rem] w-[34rem] rounded-full bg-[radial-gradient(circle_at_bottom_right,_rgba(2,6,23,0.5),_rgba(2,6,23,0.22)_38%,_transparent_74%)] blur-2xl" />
      </div>

      <header className="relative z-10 border-b border-white/10 pb-8">
        <div className="mt-6 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.35em] text-cyan-300">
              Self-hosted registry operations
            </p>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight text-white sm:text-6xl">
              Registry Control Plane
            </h1>
            <p className="mt-4 text-lg leading-8 text-slate-300">
              A production-minded control plane for sole developers and homelab
              operators who want clean registry access, scoped credentials, and
              an interface that respects the underlying Docker Distribution
              model.
            </p>
          </div>
          <Badge tone="cyan">Built to run as a small, self-hosted service</Badge>
        </div>
      </header>

      <section className="relative z-10 grid gap-6 py-10 lg:grid-cols-3">
        <Panel as="article" className="bg-white/6 p-6 shadow-2xl shadow-slate-950/30 backdrop-blur">
          <p className="text-sm font-medium text-slate-400">Operator view</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            Daily control surface
          </h2>
          <p className="mt-4 text-sm leading-7 text-slate-300">
            Sign in, review repository visibility, manage identities, and keep
            registry access in one place instead of stitching together scripts,
            htpasswd files, and one-off notes.
          </p>
          <div className="mt-6 flex gap-3">
            <Button
              as="a"
              href="/login"
            >
              Sign in
            </Button>
            <Button
              as="a"
              href="/admin"
              variant="secondary"
            >
              Admin dashboard
            </Button>
          </div>
        </Panel>

        <article className="rounded-lg border border-white/10 bg-white p-6 text-slate-900 shadow-2xl shadow-slate-950/30">
          <p className="text-sm font-medium text-slate-500">Deployment shape</p>
          <h2 className="mt-2 text-2xl font-semibold">
            Registry stays standard
          </h2>
          <p className="mt-4 text-sm leading-7 text-slate-600">
            Docker clients continue to talk on `/v2/` while the control plane
            handles auth, policy, and operator workflows separately. That keeps
            the registry path familiar and the management layer replaceable.
          </p>
          <dl className="mt-6 space-y-3 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-slate-500">Public path</dt>
              <dd className="font-semibold text-slate-900">{registryBasePath}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-slate-500">Upstream routing</dt>
              <dd className="font-semibold text-slate-900">
                Managed behind nginx
              </dd>
            </div>
          </dl>
        </article>

        <Panel as="article" className="border-emerald-400/20 bg-emerald-400/10 p-6 shadow-2xl shadow-slate-950/30">
          <p className="text-sm font-medium text-emerald-200">API ownership</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            Access model contained
          </h2>
          <p className="mt-4 text-sm leading-7 text-emerald-50/90">
            FastAPI owns users, sessions, PATs, robot tokens, scoped registry
            tokens, and permissions. Next.js stays focused on operator UX
            rather than becoming another backend in disguise.
          </p>
          <dl className="mt-6 space-y-3 text-sm text-emerald-50">
            <div className="flex items-center justify-between gap-4">
              <dt className="opacity-70">API base path</dt>
              <dd className="font-semibold">{apiBasePath}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="opacity-70">Auth token path</dt>
              <dd className="font-semibold">{authTokenPath}</dd>
            </div>
          </dl>
        </Panel>
      </section>

      <section className="relative z-10 grid gap-6 lg:grid-cols-2">
        <Panel as="article" className="border-[color:var(--line)] bg-[color:var(--surface)] p-6">
          <h2 className="text-lg font-semibold text-white">
            Production signals
          </h2>
          <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-300">
            {productionSignals.map((item) => (
              <li key={item} className="flex gap-3">
                <span className="mt-2 h-2 w-2 rounded-full bg-cyan-300" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel as="article" className="border-[color:var(--line)] bg-[color:var(--surface)] p-6">
          <h2 className="text-lg font-semibold text-white">Homelab fit</h2>
          <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-300">
            {operatorWorkflows.map((item) => (
              <li key={item} className="flex gap-3">
                <span className="mt-2 h-2 w-2 rounded-full bg-emerald-300" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </section>

      <footer className="relative z-10 mt-auto pt-10 text-center">
        <p className="text-sm text-slate-500">
          &copy; {currentYear}{" "}
          <a
            href="https://sheldylew.com"
            className="text-slate-400 transition hover:text-slate-200"
            target="_blank"
            rel="noreferrer"
          >
            sheldylew
          </a>
          . Built for experiments, shipped with restraint.
        </p>
      </footer>
    </main>
  );
}
