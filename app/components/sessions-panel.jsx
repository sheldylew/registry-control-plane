"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import Pagination from "@/app/components/ui/pagination";
import { Panel, PanelHeader } from "@/app/components/ui/panel";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

function formatDate(value) {
  if (!value) {
    return "Not set";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  return parsed.toLocaleString();
}

function statusForSession(session) {
  if (session.revoked_at) {
    return { label: "Revoked", tone: "rose" };
  }
  if (new Date(session.expires_at).getTime() <= Date.now()) {
    return { label: "Expired", tone: "amber" };
  }
  return { label: "Active", tone: "emerald" };
}

function paginationHref(page, pageSize) {
  const params = new URLSearchParams();
  if (page > 1) {
    params.set("page", String(page));
  }
  if (pageSize !== 10) {
    params.set("page_size", String(pageSize));
  }
  const query = params.toString();
  return query ? `/admin/sessions?${query}` : "/admin/sessions";
}

export default function SessionsPanel({ initialSessions, summary, pagination }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [pendingAction, setPendingAction] = useState("");

  async function postAction(path, actionId, { currentSession = false } = {}) {
    setError("");
    setPendingAction(actionId);
    const response = await fetch(path, {
      method: "POST",
      headers: {
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Could not update sessions.");
      setPendingAction("");
      return;
    }
    if (currentSession) {
      router.push("/login");
      return;
    }
    setPendingAction("");
    router.refresh();
  }

  return (
    <div className="space-y-6">
      <Panel className="p-6">
        <PanelHeader
          eyebrow="Session management"
          title="Browser sessions"
          description="Review active browser sessions and revoke stale access for users who lost a device, closed a browser offline, or need a forced sign-out."
        />
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Active sessions</p>
            <p className="mt-2 text-3xl font-semibold text-white">{summary.active_sessions}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Expired sessions</p>
            <p className="mt-2 text-3xl font-semibold text-white">{summary.expired_sessions}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Revoked sessions</p>
            <p className="mt-2 text-3xl font-semibold text-white">{summary.revoked_sessions}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Total sessions</p>
            <p className="mt-2 text-3xl font-semibold text-white">{summary.total_sessions}</p>
          </div>
        </div>
      </Panel>

      {error ? <Alert tone="rose">{error}</Alert> : null}

      <Panel className="overflow-hidden">
        <div className="divide-y divide-white/10">
          {initialSessions.length === 0 ? (
            <div className="p-6 text-sm text-slate-300">No browser sessions have been recorded.</div>
          ) : (
            initialSessions.map((session) => {
              const status = statusForSession(session);
              const revokeSessionAction = `session:${session.id}`;
              const revokeUserAction = `user:${session.user.id}`;
              const canRevokeSession = !session.revoked_at;
              const revokeUserIncludesCurrentSession = initialSessions.some(
                (candidate) => candidate.user.id === session.user.id && candidate.is_current,
              );
              return (
                <article key={session.id} className="p-6">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-lg font-semibold text-white">{session.user.username}</h3>
                        <Badge tone={status.tone}>{status.label}</Badge>
                        {session.is_current ? <Badge tone="cyan">Current session</Badge> : null}
                        {session.user.is_admin ? <Badge tone="amber">Admin</Badge> : null}
                      </div>
                      <p className="mt-1 text-sm text-slate-400">{session.user.email}</p>
                      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                        <div>
                          <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Created</dt>
                          <dd className="mt-1 text-slate-200">{formatDate(session.created_at)}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Last seen</dt>
                          <dd className="mt-1 text-slate-200">{formatDate(session.last_seen_at)}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Expires</dt>
                          <dd className="mt-1 text-slate-200">{formatDate(session.expires_at)}</dd>
                        </div>
                      </dl>
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row lg:flex-col">
                      <Button
                        type="button"
                        variant={session.is_current ? "warning" : "danger"}
                        size="sm"
                        disabled={!canRevokeSession || pendingAction === revokeSessionAction}
                        onClick={() =>
                          postAction(`/api/admin/sessions/${session.id}/revoke`, revokeSessionAction, {
                            currentSession: session.is_current,
                          })
                        }
                      >
                        {session.is_current ? "Sign out this session" : "Revoke session"}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={pendingAction === revokeUserAction}
                        onClick={() =>
                          postAction(`/api/admin/users/${session.user.id}/sessions/revoke`, revokeUserAction, {
                            currentSession: revokeUserIncludesCurrentSession,
                          })
                        }
                      >
                        Revoke user sessions
                      </Button>
                    </div>
                  </div>
                </article>
              );
            })
          )}
        </div>
      </Panel>

      <Pagination
        page={pagination.page}
        pageSize={pagination.page_size}
        total={pagination.total}
        label="sessions"
        hrefForPage={(page) => paginationHref(page, pagination.page_size)}
      />
    </div>
  );
}
