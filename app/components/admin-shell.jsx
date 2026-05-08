"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import LogoutButton from "@/app/components/logout-button";

const navItems = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/maintenance", label: "Maintenance" },
  { href: "/repos", label: "Repositories" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/tokens", label: "Tokens" },
  { href: "/admin/robots", label: "Robots" },
  { href: "/admin/audit", label: "Audit" },
  { href: "/admin/permissions", label: "Permissions" },
  { href: "/admin/settings", label: "Settings" },
];

function OpenMenuIcon(props) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M2 6.75C2 6.33579 2.33579 6 2.75 6H17.25C17.6642 6 18 6.33579 18 6.75C18 7.16421 17.6642 7.5 17.25 7.5H2.75C2.33579 7.5 2 7.16421 2 6.75ZM2 13.25C2 12.8358 2.33579 12.5 2.75 12.5H17.25C17.6642 12.5 18 12.8358 18 13.25C18 13.6642 17.6642 14 17.25 14H2.75C2.33579 14 2 13.6642 2 13.25Z" />
    </svg>
  );
}

function CloseMenuIcon(props) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
    </svg>
  );
}

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
            onClick={onNavigate}
            className={`block rounded-2xl px-4 py-3 text-sm font-medium transition ${
              active
                ? "bg-white/10 text-white"
                : "text-slate-200 hover:bg-white/5 hover:text-white"
            }`}
          >
            {item.label}
          </Link>
        </li>
      );
    });
  }

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-6 py-10 lg:px-8">
      <div
        className={`fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-sm transition duration-300 lg:hidden ${
          mobileNavOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={closeMobileNav}
        aria-hidden="true"
      />
      <div
        className={`fixed left-0 top-0 z-50 w-full max-w-80 p-3 pr-6 transition duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:hidden ${
          mobileNavOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-hidden={!mobileNavOpen}
      >
        <div className="pointer-events-none absolute inset-y-6 right-1 w-10 rounded-full bg-black/10 blur-xl" />
        <div className="relative flex max-h-[calc(100vh-1.5rem)] flex-col rounded-[1.75rem] border border-white/10 bg-slate-950/95 p-4 shadow-[0_24px_80px_rgba(2,6,23,0.55)] backdrop-blur-md">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-cyan-300">
              Navigation
            </p>
            <button
              type="button"
              onClick={closeMobileNav}
              aria-label="Close navigation"
              className="rounded-full border border-white/10 bg-white/5 p-2 text-white/80 transition hover:bg-white/10 hover:text-white"
            >
              <CloseMenuIcon className="h-5 w-5" />
            </button>
          </div>
          <nav className="overflow-y-auto rounded-3xl border border-white/10 bg-slate-900/80 p-4">
            <ul className="space-y-2">{renderNavItems(closeMobileNav)}</ul>
          </nav>
          <div className="mt-4 rounded-3xl border border-white/10 bg-slate-900/80 p-4">
            <LogoutButton />
          </div>
        </div>
      </div>

      <header className="flex flex-col gap-6 border-b border-white/10 pb-8 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.35em] text-cyan-300">
            {sectionLabel}
          </p>
          <div className="mt-4 flex items-start justify-between gap-4">
            <h1 className="text-4xl font-semibold tracking-tight text-white">
              Registry control plane
            </h1>
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open navigation"
              className="shrink-0 rounded-full border border-white/10 bg-white/5 p-2 text-white transition hover:bg-white/10 lg:hidden"
            >
              <OpenMenuIcon className="h-5 w-5" />
            </button>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            Signed in as <span className="font-semibold text-white">{user.username}</span>
          </p>
        </div>
        <div className="hidden lg:block">
          <LogoutButton />
        </div>
      </header>

      <div className="grid gap-8 pt-8 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav className="sticky top-8 hidden self-start rounded-3xl border border-white/10 bg-slate-900/80 p-4 lg:block">
          <ul className="space-y-2">{renderNavItems()}</ul>
        </nav>
        <section>{children}</section>
      </div>
    </main>
  );
}
