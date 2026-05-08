"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function MaintenancePanel({ logRetentionDays }) {
  const router = useRouter();
  const [mode, setMode] = useState("analyze");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [prunePending, setPrunePending] = useState(false);
  const [pruneError, setPruneError] = useState("");
  const [pruneMessage, setPruneMessage] = useState("");

  async function onSubmit(event) {
    event.preventDefault();
    setPending(true);
    setError("");

    const payload =
      mode === "aggressive"
        ? { dry_run: false, delete_untagged: true, prune_empty_dirs: true }
        : mode === "standard"
          ? { dry_run: false, delete_untagged: false, prune_empty_dirs: false }
          : { dry_run: true, delete_untagged: false, prune_empty_dirs: false };

    const response = await fetch("/api/admin/maintenance/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body.detail || "Unable to create maintenance job.");
      setPending(false);
      return;
    }

    router.refresh();
    setPending(false);
  }

  async function onPruneLogs() {
    setPrunePending(true);
    setPruneError("");
    setPruneMessage("");

    const response = await fetch("/api/admin/maintenance/logs/prune", {
      method: "POST",
      headers: {
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setPruneError(body.detail || "Unable to prune retained logs.");
      setPrunePending(false);
      return;
    }

    const body = await response.json();
    setPruneMessage(
      `Removed ${body.pruned.audit_events_deleted} audit events and ${body.pruned.gc_jobs_deleted} completed maintenance jobs older than ${body.retention_days} days.`,
    );
    router.refresh();
    setPrunePending(false);
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <form onSubmit={onSubmit} className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <p className="text-sm font-medium uppercase tracking-[0.22em] text-cyan-300">
          Garbage collection
        </p>
        <h2 className="mt-3 text-2xl font-semibold text-white">Schedule registry maintenance</h2>
        <p className="mt-3 text-sm leading-7 text-slate-300">
          This creates a maintenance job immediately. Only one job can run at a time.
        </p>

        <div className="mt-6 grid gap-3">
          {[
            {
              value: "analyze",
              label: "Analyze",
              detail: "Non-destructive analysis only. Records current storage usage and leaves the registry running.",
            },
            {
              value: "standard",
              label: "Run garbage collection",
              detail: "Enables the registry maintenance gate, runs official garbage collection locally, then reopens /v2/ traffic.",
            },
            {
              value: "aggressive",
              label: "Aggressive cleanup",
              detail: "Enables the registry maintenance gate, runs garbage collection with untagged cleanup, prunes empty directories, then reopens /v2/ traffic.",
            },
          ].map((option) => (
            <label
              key={option.value}
              className={`rounded-2xl border px-4 py-4 transition ${mode === option.value ? "border-cyan-400/40 bg-cyan-400/10" : "border-white/10 bg-slate-950/60"}`}
            >
              <div className="flex items-start gap-3">
                <input
                  type="radio"
                  name="gc-mode"
                  value={option.value}
                  checked={mode === option.value}
                  onChange={(event) => setMode(event.target.value)}
                  className="mt-1"
                />
                <div>
                  <p className="text-sm font-semibold text-white">{option.label}</p>
                  <p className="mt-1 text-sm text-slate-300">{option.detail}</p>
                </div>
              </div>
            </label>
          ))}
        </div>

        {error ? <p className="mt-3 text-sm text-rose-200">{error}</p> : null}

        <button
          type="submit"
          disabled={pending}
          className="mt-5 rounded-full border border-cyan-300/30 bg-cyan-400/15 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-400/25 disabled:opacity-60"
        >
          {pending ? "Submitting..." : "Create maintenance job"}
        </button>
      </form>

      <article className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <p className="text-sm font-medium uppercase tracking-[0.22em] text-cyan-300">
          Log retention
        </p>
        <h2 className="mt-3 text-2xl font-semibold text-white">Prune retained logs</h2>
        <p className="mt-3 text-sm leading-7 text-slate-300">
          Delete audit events and completed maintenance jobs older than {logRetentionDays} days without scheduling a registry maintenance run.
        </p>
        {pruneMessage ? <p className="mt-4 text-sm text-emerald-200">{pruneMessage}</p> : null}
        {pruneError ? <p className="mt-4 text-sm text-rose-200">{pruneError}</p> : null}
        <button
          type="button"
          onClick={onPruneLogs}
          disabled={prunePending}
          className="mt-5 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/10 disabled:opacity-60"
        >
          {prunePending ? "Pruning..." : "Prune old logs now"}
        </button>
      </article>
    </section>
  );
}
