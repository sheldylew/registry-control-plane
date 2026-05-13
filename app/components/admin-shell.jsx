"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArchiveBoxIcon,
  ArrowPathIcon,
  Bars3Icon,
  ChartBarSquareIcon,
  ClipboardDocumentListIcon,
  ComputerDesktopIcon,
  Cog6ToothIcon,
  CpuChipIcon,
  KeyIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";

import Button from "@/app/components/ui/button";
import LogoutButton from "@/app/components/logout-button";

const navItems = [
  { href: "/admin", label: "Overview", description: "Control-plane health", icon: ChartBarSquareIcon },
  { href: "/admin/maintenance", label: "Maintenance", description: "GC, rebuilds, retention", icon: ArrowPathIcon },
  { href: "/repos", label: "Repositories", description: "Browse images and tags", icon: ArchiveBoxIcon },
  { href: "/admin/users", label: "Users", description: "Human operators", icon: UserGroupIcon },
  { href: "/admin/sessions", label: "Sessions", description: "Browser access", icon: ComputerDesktopIcon },
  { href: "/admin/tokens", label: "Tokens", description: "Personal access", icon: KeyIcon },
  { href: "/admin/robots", label: "Robots", description: "Automation identities", icon: CpuChipIcon },
  { href: "/admin/audit", label: "Audit", description: "Identity and registry events", icon: ClipboardDocumentListIcon },
  { href: "/admin/permissions", label: "Permissions", description: "Repository access rules", icon: ShieldCheckIcon },
  { href: "/admin/settings", label: "Settings", description: "Runtime controls", icon: Cog6ToothIcon },
];

export default function AdminShell({ user, children, sectionLabel = "Admin" }) {
  const pathname = usePathname();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const visibleNavItems = user.is_admin
    ? navItems
    : navItems.filter((item) => item.href === "/repos");

  function closeMobileNav() {
    setMobileNavOpen(false);
  }

  function renderNavItems(onNavigate) {
    return visibleNavItems.map((item) => {
      const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
      const Icon = item.icon;
      return (
        <li key={item.href} className="relative">
          {active ? (
            <span
              aria-hidden="true"
              className="absolute inset-y-2 -left-4 w-0.5 rounded-full bg-white"
            />
          ) : null}
          <Link
            href={item.href}
            prefetch={false}
            onClick={onNavigate}
            className={`block rounded-lg px-4 py-3 text-sm font-medium transition ${
              active
                ? "bg-white/10 text-white"
                : "text-slate-200 hover:bg-white/5 hover:text-white"
            }`}
          >
            <span className="flex items-center gap-3">
              <span
                className={`rounded-md border p-1.5 ${
                  active
                    ? "border-cyan-300/30 bg-cyan-300/10 text-cyan-100"
                    : "border-white/10 bg-slate-950/40 text-slate-400"
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <span>{item.label}</span>
            </span>
          </Link>
        </li>
      );
    });
  }

  function renderMobileNavItems(onNavigate) {
    return visibleNavItems.map((item) => {
      const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
      const Icon = item.icon;
      return (
        <Link
          key={item.href}
          href={item.href}
          prefetch={false}
          onClick={onNavigate}
          className={`group rounded-lg border p-3 text-left transition ${
            active
              ? "border-cyan-300/40 bg-cyan-400/15 text-white shadow-lg shadow-cyan-950/20"
              : "border-white/10 bg-white/[0.04] text-slate-200 hover:border-cyan-300/30 hover:bg-white/[0.08] hover:text-white"
          }`}
        >
          <span className="flex items-start gap-3">
            <span
              className={`mt-0.5 rounded-xl border p-2.5 ${
                active
                  ? "border-cyan-300/40 bg-cyan-300/15 text-cyan-100"
                  : "border-white/10 bg-slate-950/50 text-slate-300 group-hover:text-cyan-100"
              }`}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">{item.label}</span>
              <span className="mt-1 block text-xs leading-5 text-slate-400">{item.description}</span>
            </span>
          </span>
        </Link>
      );
    });
  }

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-4 py-6 sm:px-6 sm:py-10 lg:px-8">
      <div
        className={`fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-sm transition duration-300 lg:hidden ${
          mobileNavOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={closeMobileNav}
        aria-hidden="true"
      />
      <div
        className={`fixed inset-x-0 top-0 z-50 p-3 transition duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:hidden ${
          mobileNavOpen ? "translate-y-0" : "-translate-y-full"
        }`}
        aria-hidden={!mobileNavOpen}
      >
        <div className="pointer-events-none absolute inset-x-8 top-0 h-20 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="relative max-h-[calc(100vh-1.5rem)] overflow-hidden rounded-2xl border border-white/10 bg-slate-950/95 shadow-[0_24px_80px_rgba(2,6,23,0.65)] backdrop-blur-xl">
          <div className="border-b border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.16),transparent_38%),linear-gradient(135deg,rgba(15,23,42,0.98),rgba(2,6,23,0.96))] p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.35em] text-cyan-300">
                  Command menu
                </p>
                <h2 className="mt-2 text-xl font-semibold text-white">Where to?</h2>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  Signed in as <span className="font-semibold text-white">{user.username}</span>
                </p>
              </div>
            <Button
              type="button"
              onClick={closeMobileNav}
              aria-label="Close navigation"
              variant="secondary"
              size="iconMd"
            >
              <XMarkIcon className="h-5 w-5" />
            </Button>
            </div>
          </div>
          <div className="max-h-[calc(100vh-11rem)] overflow-y-auto p-3">
            <nav aria-label="Mobile navigation">
              <div className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-2">
                {renderMobileNavItems(closeMobileNav)}
              </div>
            </nav>
            <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.04] p-3">
              <LogoutButton />
            </div>
          </div>
        </div>
      </div>

      <header className="flex flex-col gap-5 border-b border-white/10 pb-6 sm:gap-6 sm:pb-8 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.35em] text-cyan-300">
            {sectionLabel}
          </p>
          <div className="mt-4 flex items-start justify-between gap-4">
            <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              Registry control plane
            </h1>
            <Button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open navigation"
              variant="secondary"
              size="iconMd"
              className="shrink-0 lg:hidden"
            >
              <Bars3Icon className="h-5 w-5" />
            </Button>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            Signed in as <span className="font-semibold text-white">{user.username}</span>
          </p>
        </div>
        <div className="hidden lg:block">
          <LogoutButton />
        </div>
      </header>

      <div className="grid gap-6 pt-6 sm:gap-8 sm:pt-8 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav className="sticky top-8 hidden self-start rounded-lg border border-white/10 bg-slate-900/80 p-4 lg:block">
          <ul className="space-y-2">{renderNavItems()}</ul>
        </nav>
        <section>{children}</section>
      </div>
    </main>
  );
}
