"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { useRouter } from "next/navigation";

import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import DetailList from "@/app/components/ui/detail-list";
import EmptyState from "@/app/components/ui/empty-state";
import FormDialog from "@/app/components/ui/form-dialog";
import { Field, Input } from "@/app/components/ui/form";
import Pagination from "@/app/components/ui/pagination";
import { MobileCollapsiblePanel, Panel, PanelHeader } from "@/app/components/ui/panel";
import Switch from "@/app/components/ui/switch";
import { MobileDisclosureCard, MobileField } from "@/app/components/ui/table";
import { formatDateTime } from "@/app/lib/date-format";
import { isValidPassword, readApiErrorDetail } from "@/app/lib/user-form";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function UserProfilePanel({ user, tokens, permissions, recentActivity, activityPagination, currentUserId, timeZone }) {
  const router = useRouter();
  const [passwordResetUser] = useState(user);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [resetPending, setResetPending] = useState(false);
  const [resetError, setResetError] = useState("");
  const [resetOpen, setResetOpen] = useState(false);
  const [statusPending, setStatusPending] = useState(false);
  const [statusError, setStatusError] = useState("");
  const resettingOwnPassword = passwordResetUser?.id === currentUserId;
  const canResetPassword = (
    (!resettingOwnPassword || isValidPassword(currentPassword, 1))
    && isValidPassword(newPassword)
    && newPassword === confirmPassword
  );

  function buildActivityPageHref(page) {
    const params = new URLSearchParams();
    params.set("activity_page", String(page));
    return `/admin/users/${encodeURIComponent(user.id)}?${params.toString()}`;
  }

  function openPasswordReset() {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setResetError("");
    setResetOpen(true);
  }

  function closePasswordReset() {
    if (resetPending) {
      return;
    }
    setResetOpen(false);
    setResetError("");
  }

  async function setUserActive(nextActive) {
    if (user.id === currentUserId && !nextActive) {
      return;
    }

    setStatusPending(true);
    setStatusError("");
    const response = await fetch(`/api/admin/users/${user.id}/${nextActive ? "enable" : "disable"}`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setStatusError(readApiErrorDetail(payload, `Could not ${nextActive ? "enable" : "disable"} user.`));
      setStatusPending(false);
      return;
    }
    setStatusPending(false);
    router.refresh();
  }

  async function resetUserPassword(event) {
    event.preventDefault();
    if (resettingOwnPassword && !isValidPassword(currentPassword, 1)) {
      setResetError("Current password is required.");
      return;
    }
    if (!isValidPassword(newPassword)) {
      setResetError("Password must be at least 8 characters and not only whitespace.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setResetError("Passwords must match.");
      return;
    }

    setResetPending(true);
    setResetError("");
    const response = await fetch(`/api/admin/users/${user.id}/password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({
        password: newPassword,
        current_password: resettingOwnPassword ? currentPassword : undefined,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setResetError(readApiErrorDetail(payload, "Could not reset password."));
      setResetPending(false);
      return;
    }

    setResetPending(false);
    setResetOpen(false);
    if (resettingOwnPassword) {
      router.push("/");
      return;
    }
    router.refresh();
  }

  return (
    <>
      <div className="space-y-6">
        <Panel className="p-4 sm:p-6">
          <PanelHeader
            eyebrow="User profile"
            title={user.username}
            description="This profile keeps presentation data visible while mutations stay in focused controls."
            action={(
              <div className="grid gap-2 sm:flex sm:flex-wrap sm:justify-end">
                <Button as={Link} href="/admin/users" prefetch={false} variant="secondary" size="sm" className="w-full sm:w-auto">
                  Back to users
                </Button>
                <Button type="button" onClick={openPasswordReset} size="sm" className="w-full sm:w-auto">
                  Reset password
                </Button>
              </div>
            )}
          />
          {statusError ? <Alert tone="rose" className="mt-6">{statusError}</Alert> : null}
          <div className="mt-6">
            <DetailList
              items={[
                { label: "Email", value: user.email },
                { label: "Role", value: <Badge tone={user.is_admin ? "cyan" : "slate"}>{user.is_admin ? "Admin" : "User"}</Badge> },
                { label: "Status", value: <Badge tone={user.is_active ? "emerald" : "amber"} dot>{user.is_active ? "Active" : "Disabled"}</Badge> },
                { label: "Tokens", value: `${tokens.length} issued` },
                { label: "Permissions", value: `${permissions.length} rules` },
                {
                  label: "Access control",
                  value: (
                    <Switch
                      checked={user.is_active}
                      onChange={setUserActive}
                      disabled={user.id === currentUserId && user.is_active}
                      loading={statusPending}
                      label={user.is_active ? "Enabled" : "Disabled"}
                      description={user.id === currentUserId ? "Current signed-in operator" : "Toggle access"}
                      align="start"
                    />
                  ),
                },
              ]}
            />
          </div>
        </Panel>

        <MobileCollapsiblePanel className="p-4 sm:p-6" title="Personal access tokens" summaryMeta={`${tokens.length} issued`}>
          <PanelHeader title="Personal access tokens" description="Issued CLI credentials for this user." />
          <div className="mt-4 space-y-3">
            {tokens.length ? tokens.map((token) => (
              <Fragment key={token.id}>
              <MobileDisclosureCard
                className="lg:hidden"
                summary={(
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-white">{token.name}</p>
                      <Badge tone={token.revoked_at ? "amber" : "emerald"} dot>
                        {token.revoked_at ? "Revoked" : "Active"}
                      </Badge>
                    </div>
                    <p className="mt-1 truncate font-mono text-xs text-slate-400">prefix: {token.token_prefix}</p>
                  </div>
                )}
              >
                <dl className="grid gap-3">
                  <MobileField label="Token prefix"><span className="break-all font-mono">{token.token_prefix}</span></MobileField>
                  <MobileField label="Issued">{formatDateTime(token.created_at, { timeZone })}</MobileField>
                </dl>
              </MobileDisclosureCard>
              <div className="hidden rounded-lg border border-white/10 bg-slate-950/60 px-4 py-4 lg:block">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                  <div>
                    <p className="text-sm font-semibold text-white">{token.name}</p>
                    <p className="mt-1 font-mono text-xs text-slate-400">prefix: {token.token_prefix}</p>
                  </div>
                  <Badge tone={token.revoked_at ? "amber" : "emerald"} dot>
                    {token.revoked_at ? "Revoked" : "Active"}
                  </Badge>
                </div>
                <p className="mt-3 text-xs text-slate-500">Issued {formatDateTime(token.created_at, { timeZone })}</p>
              </div>
              </Fragment>
            )) : (
              <EmptyState title="No personal access tokens" description="No CLI credentials have been issued for this user." />
            )}
          </div>
        </MobileCollapsiblePanel>

        <MobileCollapsiblePanel className="p-4 sm:p-6" title="Repository permissions" summaryMeta={`${permissions.length} rules`}>
          <PanelHeader title="Repository permissions" description="Current repository access rules for this user." />
          <div className="mt-4 space-y-3">
            {permissions.length ? permissions.map((permission) => (
              <Fragment key={permission.id}>
              <MobileDisclosureCard
                className="lg:hidden"
                summary={(
                  <div>
                    <p className="break-all font-mono text-sm text-white">{permission.repository_pattern}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {permission.can_pull ? <Badge tone="emerald">Pull</Badge> : null}
                      {permission.can_push ? <Badge tone="cyan">Push</Badge> : null}
                      {permission.can_delete ? <Badge tone="amber">Delete tag</Badge> : null}
                    </div>
                  </div>
                )}
              >
                <div className="flex flex-wrap gap-2">
                  <Badge tone={permission.can_pull ? "emerald" : "slate"}>{permission.can_pull ? "Pull" : "No pull"}</Badge>
                  <Badge tone={permission.can_push ? "cyan" : "slate"}>{permission.can_push ? "Push" : "No push"}</Badge>
                  <Badge tone={permission.can_delete ? "amber" : "slate"}>{permission.can_delete ? "Delete tag" : "No delete"}</Badge>
                </div>
              </MobileDisclosureCard>
              <div className="hidden rounded-lg border border-white/10 bg-slate-950/60 px-4 py-4 lg:block">
                <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-4">
                  <p className="break-all font-mono text-sm text-white">{permission.repository_pattern}</p>
                  <div className="flex flex-wrap gap-2">
                    <Badge tone={permission.can_pull ? "emerald" : "slate"}>{permission.can_pull ? "Pull" : "No pull"}</Badge>
                    <Badge tone={permission.can_push ? "cyan" : "slate"}>{permission.can_push ? "Push" : "No push"}</Badge>
                    <Badge tone={permission.can_delete ? "amber" : "slate"}>{permission.can_delete ? "Delete tag" : "No delete"}</Badge>
                  </div>
                </div>
              </div>
              </Fragment>
            )) : (
              <EmptyState title="No repository permissions" description="This user does not currently have explicit repository access rules." />
            )}
          </div>
        </MobileCollapsiblePanel>

        <MobileCollapsiblePanel className="p-4 sm:p-6" title="Recent activity" summaryMeta={`${recentActivity.length} events`}>
          <PanelHeader title="Recent activity" description="Latest user-related audit events." />
          <div className="mt-4 space-y-3">
            {recentActivity.length ? recentActivity.map((event) => (
              <Fragment key={event.id}>
              <MobileDisclosureCard
                className="lg:hidden"
                summary={(
                  <div>
                    <p className="text-sm font-medium text-white">{event.action}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">{formatDateTime(event.created_at, { timeZone })}</p>
                  </div>
                )}
              >
                <MobileField label="Actor">{event.actor_label || event.actor_type}</MobileField>
              </MobileDisclosureCard>
              <div className="hidden rounded-lg border border-white/10 bg-slate-950/60 px-4 py-4 lg:block">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                  <p className="text-sm font-medium text-white">{event.action}</p>
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{formatDateTime(event.created_at, { timeZone })}</p>
                </div>
                <p className="mt-2 text-sm text-slate-400">
                  Actor: {event.actor_label || event.actor_type}
                </p>
              </div>
              </Fragment>
            )) : (
              <EmptyState title="No recent activity" description="No user-related audit events were found for this profile." />
            )}
          </div>
          {activityPagination ? (
            <Pagination
              page={activityPagination.page}
              pageSize={activityPagination.page_size}
              total={activityPagination.total}
              label="activity events"
              hrefForPage={buildActivityPageHref}
            />
          ) : null}
        </MobileCollapsiblePanel>
      </div>

      <FormDialog
        open={resetOpen}
        onClose={closePasswordReset}
        eyebrow="User management"
        title={`Reset ${user.username} password`}
        description="Keep credential changes in a focused edit flow instead of the default profile view."
        onSubmit={resetUserPassword}
        submitLabel="Reset password"
        submitPendingLabel="Resetting..."
        pending={resetPending}
        disabled={!canResetPassword}
        error={resetError}
      >
        {resettingOwnPassword ? (
          <Field label="Current password">
            <Input
              autoFocus
              type="password"
              placeholder="Current password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              required
            />
          </Field>
        ) : null}
        <Field label="New password">
          <Input
            autoFocus={!resettingOwnPassword}
            type="password"
            placeholder="New password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            required
            minLength={8}
          />
        </Field>
        <Field label="Confirm password">
          <Input
            type="password"
            placeholder="Confirm password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            minLength={8}
          />
        </Field>
        {resettingOwnPassword ? (
          <Alert tone="amber">
            Resetting your own password signs out this browser session.
          </Alert>
        ) : null}
      </FormDialog>
    </>
  );
}
