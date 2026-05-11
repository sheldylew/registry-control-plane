"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ArrowPathIcon } from "@heroicons/react/20/solid";

import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import { Panel, PanelHeader } from "@/app/components/ui/panel";

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
  const [rebuildPending, setRebuildPending] = useState(false);
  const [rebuildError, setRebuildError] = useState("");
  const [rebuildMessage, setRebuildMessage] = useState("");

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

    setPending(false);
    router.refresh();
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
      `Removed ${body.pruned.audit_events_deleted} audit events, ${body.pruned.gc_jobs_deleted} completed maintenance jobs, ${body.pruned.web_sessions_deleted} browser sessions, ${body.pruned.personal_access_tokens_deleted} PAT records, and ${body.pruned.robot_tokens_deleted} robot token records past retention.`,
    );
    setPrunePending(false);
    router.refresh();
  }

  async function onRebuildCache() {
    setRebuildPending(true);
    setRebuildError("");
    setRebuildMessage("");

    const response = await fetch("/api/admin/maintenance/cache/rebuild", {
      method: "POST",
      headers: {
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setRebuildError(body.detail || "Unable to start registry state rebuild.");
      setRebuildPending(false);
      return;
    }

    const body = await response.json();
    setRebuildMessage(`Rebuild job #${body.job.id} ${body.job.status}.`);
    setRebuildPending(false);
    router.refresh();
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Panel as="form" onSubmit={onSubmit} className="p-6">
        <PanelHeader
          eyebrow="Garbage collection"
          title="Schedule registry maintenance"
          description="This creates a maintenance job immediately. Only one job can run at a time."
        />

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
              className={`rounded-lg border px-4 py-4 transition ${mode === option.value ? "border-cyan-400/40 bg-cyan-400/10" : "border-white/10 bg-slate-950/60"}`}
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

        {error ? <Alert tone="rose" className="mt-3">{error}</Alert> : null}

        <Button
          type="submit"
          disabled={pending}
          loading={pending}
          variant="soft"
          className="mt-5"
        >
          {pending ? "Submitting..." : "Create maintenance job"}
        </Button>
      </Panel>

      <div className="space-y-6">
        <Panel as="article" className="p-6">
          <PanelHeader
            eyebrow="Registry state"
            title="Rebuild registry state"
            description="Walk the registry catalog, refresh repository/tag state, and repair missed notification updates."
          />
          {rebuildMessage ? <Alert tone="emerald" className="mt-4">{rebuildMessage}</Alert> : null}
          {rebuildError ? <Alert tone="rose" className="mt-4">{rebuildError}</Alert> : null}
          <Button
            type="button"
            onClick={onRebuildCache}
            disabled={rebuildPending}
            loading={rebuildPending}
            variant="soft"
            className="mt-5"
          >
            {rebuildPending ? null : <ArrowPathIcon className="h-4 w-4" />}
            {rebuildPending ? "Starting..." : "Rebuild registry state"}
          </Button>
        </Panel>

        <Panel as="article" className="p-6">
          <PanelHeader
            eyebrow="Log retention"
            title="Prune retained logs"
            description={`Delete audit events and completed maintenance jobs older than ${logRetentionDays} days without scheduling a registry maintenance run.`}
            action={<Badge tone="cyan">{logRetentionDays} days</Badge>}
          />
          {pruneMessage ? <Alert tone="emerald" className="mt-4">{pruneMessage}</Alert> : null}
          {pruneError ? <Alert tone="rose" className="mt-4">{pruneError}</Alert> : null}
          <Button
            type="button"
            onClick={onPruneLogs}
            disabled={prunePending}
            loading={prunePending}
            variant="secondary"
            className="mt-5"
          >
            {prunePending ? "Pruning..." : "Prune old logs now"}
          </Button>
        </Panel>
      </div>
    </section>
  );
}
