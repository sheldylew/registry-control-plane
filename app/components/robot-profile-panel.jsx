"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import DetailList from "@/app/components/ui/detail-list";
import EmptyState from "@/app/components/ui/empty-state";
import FormDialog from "@/app/components/ui/form-dialog";
import { Field, Input } from "@/app/components/ui/form";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import Switch from "@/app/components/ui/switch";
import RepoDeletePanel from "@/app/components/repo-delete-panel";
import { formatDateTime } from "@/app/lib/date-format";
import { hasNonEmptyValue, normalizeTextInput, readApiErrorDetail } from "@/app/lib/user-form";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function RobotProfilePanel({ robot, permissions, recentActivity, timeZone }) {
  const router = useRouter();
  const [tokenName, setTokenName] = useState("default");
  const [tokenOpen, setTokenOpen] = useState(false);
  const [latestToken, setLatestToken] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [statusPending, setStatusPending] = useState(false);
  const [statusError, setStatusError] = useState("");
  const canCreateToken = hasNonEmptyValue(tokenName);
  const activeTokenCount = robot.tokens.filter((token) => !token.revoked_at).length;

  function openTokenDialog() {
    setTokenName("default");
    setError("");
    setTokenOpen(true);
  }

  function closeTokenDialog() {
    if (pending) {
      return;
    }
    setTokenOpen(false);
    setError("");
  }

  async function createRobotToken(event) {
    event.preventDefault();
    const normalizedName = normalizeTextInput(tokenName);
    if (!normalizedName) {
      setError("Token name is required.");
      return;
    }

    setPending(true);
    setError("");
    const response = await fetch(`/api/admin/robots/${robot.id}/tokens`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({ name: normalizedName }),
    });
    const payload = await response.json().catch(() => ({}));
    setPending(false);
    if (response.ok) {
      setLatestToken(payload.raw_token);
      setTokenOpen(false);
      setTokenName("default");
      router.refresh();
      return;
    }
    setError(readApiErrorDetail(payload, "Could not create robot token."));
  }

  async function revokeRobotToken(tokenId) {
    setStatusError("");
    const response = await fetch(`/api/admin/robots/${robot.id}/tokens/${tokenId}/revoke`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setStatusError(payload.detail || "Could not revoke robot token.");
      return;
    }
    router.refresh();
  }

  async function setRobotActive(nextActive) {
    setStatusPending(true);
    setStatusError("");
    const response = await fetch(`/api/admin/robots/${robot.id}/${nextActive ? "enable" : "disable"}`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setStatusError(payload.detail || `Could not ${nextActive ? "enable" : "disable"} robot.`);
      setStatusPending(false);
      return;
    }
    setStatusPending(false);
    router.refresh();
  }

  return (
    <>
      <div className="space-y-6">
        <Panel className="p-6">
          <PanelHeader
            eyebrow="Robot profile"
            title={robot.name}
            description="This profile keeps the robot state readable while token and access changes stay in focused flows."
            action={(
              <div className="flex flex-wrap justify-end gap-2">
                <Button as={Link} href="/admin/robots" prefetch={false} variant="secondary" size="sm">
                  Back to robots
                </Button>
                <Button type="button" onClick={openTokenDialog} size="sm">
                  Create token
                </Button>
              </div>
            )}
          />
          {latestToken ? (
            <Alert tone="emerald" className="mt-6">
              <Badge tone="emerald">Robot token</Badge>
              <p className="mt-2 break-all font-mono text-sm text-white">{latestToken}</p>
            </Alert>
          ) : null}
          {statusError ? <Alert tone="rose" className="mt-6">{statusError}</Alert> : null}
          <div className="mt-6">
            <DetailList
              items={[
                { label: "Description", value: robot.description || "No description." },
                { label: "Status", value: <Badge tone={robot.is_active ? "emerald" : "amber"} dot>{robot.is_active ? "Active" : "Disabled"}</Badge> },
                { label: "Active tokens", value: `${activeTokenCount} active token${activeTokenCount === 1 ? "" : "s"}` },
                { label: "Permissions", value: `${permissions.length} rules` },
                {
                  label: "Access control",
                  value: (
                    <Switch
                      checked={robot.is_active}
                      onChange={setRobotActive}
                      disabled={statusPending}
                      label={robot.is_active ? "Enabled" : "Disabled"}
                      description="Toggle robot access"
                      align="start"
                    />
                  ),
                },
                {
                  label: "Delete robot",
                  value: (
                    <RepoDeletePanel
                      title={`Delete robot ${robot.name}`}
                      description="This permanently removes the robot account and all of its tokens."
                      confirmationLabel="Type the robot name to confirm"
                      confirmationValue={robot.name}
                      endpoint={`/api/admin/robots/${robot.id}/delete`}
                      buttonLabel="Delete robot"
                      successLabel="Deleting..."
                      redirectPath="/admin/robots"
                    />
                  ),
                },
              ]}
            />
          </div>
        </Panel>

        <Panel className="p-6">
          <PanelHeader title="Robot tokens" description="Issued credentials for this automation identity." />
          <div className="mt-4 space-y-3">
            {robot.tokens.length ? robot.tokens.map((token) => (
              <div key={token.id} className="rounded-lg border border-white/10 bg-slate-950/60 px-4 py-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-white">{token.name}</p>
                    <p className="mt-1 font-mono text-xs text-slate-400">prefix: {token.token_prefix}</p>
                  </div>
                  {token.revoked_at ? (
                    <Badge tone="amber" dot>Revoked</Badge>
                  ) : (
                    <Button type="button" onClick={() => revokeRobotToken(token.id)} variant="warning" size="xs">
                      Revoke
                    </Button>
                  )}
                </div>
                <p className="mt-3 text-xs text-slate-500">Issued {formatDateTime(token.created_at, { timeZone })}</p>
              </div>
            )) : (
              <EmptyState title="No robot tokens" description="No robot credentials have been issued yet." />
            )}
          </div>
        </Panel>

        <Panel className="p-6">
          <PanelHeader title="Repository permissions" description="Current repository access rules for this robot." />
          <div className="mt-4 space-y-3">
            {permissions.length ? permissions.map((permission) => (
              <div key={permission.id} className="rounded-lg border border-white/10 bg-slate-950/60 px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <p className="font-mono text-sm text-white">{permission.repository_pattern}</p>
                  <div className="flex flex-wrap gap-2">
                    <Badge tone={permission.can_pull ? "emerald" : "slate"}>{permission.can_pull ? "Pull" : "No pull"}</Badge>
                    <Badge tone={permission.can_push ? "cyan" : "slate"}>{permission.can_push ? "Push" : "No push"}</Badge>
                    <Badge tone={permission.can_delete ? "amber" : "slate"}>{permission.can_delete ? "Delete tag" : "No delete"}</Badge>
                  </div>
                </div>
              </div>
            )) : (
              <EmptyState title="No repository permissions" description="This robot does not currently have explicit repository access rules." />
            )}
          </div>
        </Panel>

        <Panel className="p-6">
          <PanelHeader title="Recent activity" description="Latest robot-related audit events." />
          <div className="mt-4 space-y-3">
            {recentActivity.length ? recentActivity.map((event) => (
              <div key={event.id} className="rounded-lg border border-white/10 bg-slate-950/60 px-4 py-4">
                <div className="flex items-center justify-between gap-4">
                  <p className="text-sm font-medium text-white">{event.action}</p>
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{formatDateTime(event.created_at, { timeZone })}</p>
                </div>
                <p className="mt-2 text-sm text-slate-400">
                  Actor: {event.actor_label || event.actor_type}
                </p>
              </div>
            )) : (
              <EmptyState title="No recent activity" description="No robot-related audit events were found for this profile." />
            )}
          </div>
        </Panel>
      </div>

      <FormDialog
        open={tokenOpen}
        onClose={closeTokenDialog}
        eyebrow="Robots"
        title={`Create token for ${robot.name}`}
        description="The raw secret is shown once after creation."
        onSubmit={createRobotToken}
        submitLabel="Create token"
        submitPendingLabel="Creating..."
        pending={pending}
        disabled={!canCreateToken}
        error={error}
      >
        <Field label="Token name">
          <Input
            autoFocus
            placeholder="default"
            value={tokenName}
            onChange={(event) => setTokenName(event.target.value)}
            required
          />
        </Field>
      </FormDialog>
    </>
  );
}
