"use client";

import { useRouter } from "next/navigation";
import { Fragment, useState } from "react";

import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import Pagination from "@/app/components/ui/pagination";
import { MobileCollapsiblePanel, Panel, PanelHeader } from "@/app/components/ui/panel";
import { MobileDisclosureCard, MobileField } from "@/app/components/ui/table";
import { formatDateTime } from "@/app/lib/date-format";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
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

export default function SessionsPanel({ initialSessions, summary, pagination, timeZone }) {
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
      router.push("/");
      return;
    }
    setPendingAction("");
    router.refresh();
  }

  return (
    <div className="space-y-6">
      <Panel className="p-4 sm:p-6">
        <PanelHeader
          eyebrow="Session management"
          title="Browser sessions"
          description="Review active browser sessions and revoke stale access for users who lost a device, closed a browser offline, or need a forced sign-out."
        />
        <div className="mt-5 grid grid-cols-2 gap-3 sm:mt-6 sm:gap-4 lg:grid-cols-4">
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Active sessions</p>
            <p className="mt-2 text-2xl font-semibold text-white sm:text-3xl">{summary.active_sessions}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Expired sessions</p>
            <p className="mt-2 text-2xl font-semibold text-white sm:text-3xl">{summary.expired_sessions}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Revoked sessions</p>
            <p className="mt-2 text-2xl font-semibold text-white sm:text-3xl">{summary.revoked_sessions}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Total sessions</p>
            <p className="mt-2 text-2xl font-semibold text-white sm:text-3xl">{summary.total_sessions}</p>
          </div>
        </div>
      </Panel>

      {error ? <Alert tone="rose">{error}</Alert> : null}

      <MobileCollapsiblePanel className="overflow-hidden" title="Browser session list" summaryMeta={`${pagination.total} sessions`}>
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
                <Fragment key={session.id}>
                <MobileDisclosureCard
                  className="mx-4 my-4 lg:hidden"
                  summary={(
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold text-white">{session.user.username}</h3>
                        <Badge tone={status.tone}>{status.label}</Badge>
                        {session.is_current ? <Badge tone="cyan">Current</Badge> : null}
                        {session.user.is_admin ? <Badge tone="amber">Admin</Badge> : null}
                      </div>
                      <p className="mt-1 truncate text-sm text-slate-400">{session.user.email}</p>
                    </div>
                  )}
                >
                  <dl className="grid gap-3">
                    <MobileField label="Created">{formatDateTime(session.created_at, { timeZone, fallback: "Not set" })}</MobileField>
                    <MobileField label="Last seen">{formatDateTime(session.last_seen_at, { timeZone, fallback: "Not set" })}</MobileField>
                    <MobileField label="Expires">{formatDateTime(session.expires_at, { timeZone, fallback: "Not set" })}</MobileField>
                  </dl>
                  <div className="mt-4 grid gap-2">
                    <Button
                      type="button"
                      variant={session.is_current ? "warning" : "danger"}
                      size="sm"
                      disabled={!canRevokeSession || pendingAction === revokeSessionAction}
                      loading={pendingAction === revokeSessionAction}
                      onClick={() =>
                        postAction(`/api/admin/sessions/${session.id}/revoke`, revokeSessionAction, {
                          currentSession: session.is_current,
                        })
                      }
                      className="w-full"
                    >
                      {session.is_current ? "Sign out this session" : "Revoke session"}
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={pendingAction === revokeUserAction}
                      loading={pendingAction === revokeUserAction}
                      onClick={() =>
                        postAction(`/api/admin/users/${session.user.id}/sessions/revoke`, revokeUserAction, {
                          currentSession: revokeUserIncludesCurrentSession,
                        })
                      }
                      className="w-full"
                    >
                      Revoke user sessions
                    </Button>
                  </div>
                </MobileDisclosureCard>
                <article className="hidden p-4 sm:p-6 lg:block">
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
                          <dd className="mt-1 text-slate-200">{formatDateTime(session.created_at, { timeZone, fallback: "Not set" })}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Last seen</dt>
                          <dd className="mt-1 text-slate-200">{formatDateTime(session.last_seen_at, { timeZone, fallback: "Not set" })}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase tracking-[0.16em] text-slate-500">Expires</dt>
                          <dd className="mt-1 text-slate-200">{formatDateTime(session.expires_at, { timeZone, fallback: "Not set" })}</dd>
                        </div>
                      </dl>
                    </div>
                    <div className="grid gap-2 sm:flex sm:flex-row lg:flex-col">
                      <Button
                        type="button"
                        variant={session.is_current ? "warning" : "danger"}
                        size="sm"
                        disabled={!canRevokeSession || pendingAction === revokeSessionAction}
                        loading={pendingAction === revokeSessionAction}
                        onClick={() =>
                          postAction(`/api/admin/sessions/${session.id}/revoke`, revokeSessionAction, {
                            currentSession: session.is_current,
                          })
                        }
                        className="w-full sm:w-auto lg:w-full"
                      >
                        {session.is_current ? "Sign out this session" : "Revoke session"}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={pendingAction === revokeUserAction}
                        loading={pendingAction === revokeUserAction}
                        onClick={() =>
                          postAction(`/api/admin/users/${session.user.id}/sessions/revoke`, revokeUserAction, {
                            currentSession: revokeUserIncludesCurrentSession,
                          })
                        }
                        className="w-full sm:w-auto lg:w-full"
                      >
                        Revoke user sessions
                      </Button>
                    </div>
                  </div>
                </article>
                </Fragment>
              );
            })
          )}
        </div>
      </MobileCollapsiblePanel>

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
