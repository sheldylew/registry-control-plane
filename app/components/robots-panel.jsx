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
import {
  FORM_DESCRIPTION_MAX_LENGTH,
  FORM_NAME_MAX_LENGTH,
  hasNonEmptyValue,
  normalizeTextInput,
  readApiErrorDetail,
} from "@/app/lib/user-form";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function RobotsPanel({ initialRobots }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tokenName, setTokenName] = useState("default");
  const [selectedRobot, setSelectedRobot] = useState(null);
  const [latestToken, setLatestToken] = useState("");
  const [error, setError] = useState("");
  const [statusError, setStatusError] = useState("");
  const [pending, setPending] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [tokenOpen, setTokenOpen] = useState(false);
  const [pendingRobotId, setPendingRobotId] = useState(null);
  const [pendingTokenId, setPendingTokenId] = useState(null);
  const canCreateRobot = hasNonEmptyValue(name);
  const canCreateRobotToken = hasNonEmptyValue(tokenName);

  function openCreateDialog() {
    setError("");
    setCreateOpen(true);
  }

  function closeCreateDialog() {
    if (pending) {
      return;
    }
    setCreateOpen(false);
    setError("");
  }

  function openTokenDialog(robot) {
    setSelectedRobot(robot);
    setTokenName("default");
    setError("");
    setTokenOpen(true);
  }

  function closeTokenDialog() {
    if (pending) {
      return;
    }
    setSelectedRobot(null);
    setTokenName("default");
    setError("");
    setTokenOpen(false);
  }

  async function createRobot(event) {
    event.preventDefault();
    const normalizedName = normalizeTextInput(name);
    if (!normalizedName) {
      setError("Robot name is required.");
      return;
    }

    setPending(true);
    setError("");
    const response = await fetch("/api/admin/robots", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({
        name: normalizedName,
        description: normalizeTextInput(description),
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(readApiErrorDetail(payload, "Could not create robot."));
      setPending(false);
      return;
    }
    setName("");
    setDescription("");
    setPending(false);
    setCreateOpen(false);
    router.refresh();
  }

  async function createRobotToken(event) {
    event.preventDefault();
    if (!selectedRobot) {
      return;
    }

    const normalizedName = normalizeTextInput(tokenName);
    if (!normalizedName) {
      setError("Token name is required.");
      return;
    }

    setPending(true);
    setError("");
    const response = await fetch(`/api/admin/robots/${selectedRobot.id}/tokens`, {
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
      setSelectedRobot(null);
      setTokenName("default");
      router.refresh();
      return;
    }
    setError(readApiErrorDetail(payload, "Could not create robot token."));
  }

  async function revokeRobotToken(robotId, tokenId) {
    setStatusError("");
    setPendingTokenId(tokenId);
    const response = await fetch(`/api/admin/robots/${robotId}/tokens/${tokenId}/revoke`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setStatusError(payload.detail || "Could not revoke robot token.");
      setPendingTokenId(null);
      return;
    }
    setPendingTokenId(null);
    router.refresh();
  }

  async function setRobotActive(robot, nextActive) {
    setPendingRobotId(robot.id);
    setStatusError("");
    const response = await fetch(`/api/admin/robots/${robot.id}/${nextActive ? "enable" : "disable"}`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setStatusError(payload.detail || `Could not ${nextActive ? "enable" : "disable"} robot.`);
      setPendingRobotId(null);
      return;
    }
    setPendingRobotId(null);
    router.refresh();
  }

  return (
    <>
      <div className="space-y-6">
        <Panel className="p-6">
          <PanelHeader
            title="Robot accounts"
            description="Keep robot administration in presentation mode by default, then use focused create and token flows when automation needs change."
            action={(
              <Button type="button" onClick={openCreateDialog} size="lg">
                Create robot
              </Button>
            )}
          />
          {latestToken ? (
            <Alert tone="emerald" className="mt-6">
              <Badge tone="emerald">Robot token</Badge>
              <p className="mt-2 break-all font-mono text-sm text-white">{latestToken}</p>
            </Alert>
          ) : null}
          {statusError ? <Alert tone="rose" className="mt-6">{statusError}</Alert> : null}
        </Panel>

        <div className="space-y-4">
          {initialRobots.length ? initialRobots.map((robot) => {
            const activeTokenCount = robot.tokens.filter((token) => !token.revoked_at).length;
            return (
              <Panel
                as="article"
                key={robot.id}
                className="p-6"
              >
                <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex items-center gap-3">
                      <Link prefetch={false} href={`/admin/robots/${robot.id}`} className="text-lg font-semibold text-white transition hover:text-cyan-200">
                        {robot.name}
                      </Link>
                      <Badge tone={robot.is_active ? "emerald" : "amber"} dot>
                        {robot.is_active ? "Active" : "Disabled"}
                      </Badge>
                    </div>
                    <p className="mt-2 text-sm text-slate-300">{robot.description || "No description."}</p>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <Button as={Link} href={`/admin/robots/${robot.id}`} prefetch={false} variant="soft" size="xs">
                      View profile
                    </Button>
                    <Button
                      type="button"
                      onClick={() => openTokenDialog(robot)}
                      variant="secondary"
                      size="xs"
                    >
                      Create token
                    </Button>
                    <RepoDeletePanel
                      title={`Delete robot ${robot.name}`}
                      description="This permanently removes the robot account and all of its tokens."
                      confirmationLabel="Type the robot name to confirm"
                      confirmationValue={robot.name}
                      endpoint={`/api/admin/robots/${robot.id}/delete`}
                      buttonLabel="Delete robot"
                      successLabel="Deleting..."
                      redirectPath="/admin/robots"
                      compact
                    />
                  </div>
                </div>

                <div className="mt-5">
                  <DetailList
                    compact
                    items={[
                      {
                        label: "Status control",
                        value: (
                          <Switch
                            checked={robot.is_active}
                            onChange={(nextActive) => setRobotActive(robot, nextActive)}
                            loading={pendingRobotId === robot.id}
                            label={robot.is_active ? "Enabled" : "Disabled"}
                            description="Toggle robot access"
                            align="start"
                          />
                        ),
                      },
                      {
                        label: "Active tokens",
                        value: `${activeTokenCount} active token${activeTokenCount === 1 ? "" : "s"}`,
                      },
                    ]}
                  />
                </div>

                <ul className="mt-4 space-y-2">
                  {robot.tokens.length ? robot.tokens.map((token) => (
                    <li
                      key={token.id}
                      className="flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-slate-300"
                    >
                      <div>
                        <span>{token.name} • prefix {token.token_prefix}</span>
                        {token.revoked_at ? (
                          <span className="ml-3">
                            <Badge>Revoked</Badge>
                          </span>
                        ) : null}
                      </div>
                      {!token.revoked_at ? (
                        <Button
                          type="button"
                          onClick={() => revokeRobotToken(robot.id, token.id)}
                          variant="warning"
                          size="xs"
                          loading={pendingTokenId === token.id}
                        >
                          Revoke
                        </Button>
                      ) : null}
                    </li>
                  )) : (
                    <li className="rounded-lg border border-dashed border-white/10 bg-slate-950/40 px-4 py-4 text-sm text-slate-400">
                      No tokens issued yet.
                    </li>
                  )}
                </ul>
              </Panel>
            );
          }) : (
            <EmptyState
              title="No robot accounts"
              description="Create a robot account when automation needs registry access."
              action={(
                <Button type="button" onClick={openCreateDialog}>
                  Create robot
                </Button>
              )}
            />
          )}
        </div>
      </div>

      <FormDialog
        open={createOpen}
        onClose={closeCreateDialog}
        eyebrow="Robots"
        title="Create robot account"
        description="Create the robot first, then manage its tokens and access from the profile view."
        onSubmit={createRobot}
        submitLabel="Create robot"
        submitPendingLabel="Creating..."
        pending={pending}
        disabled={!canCreateRobot}
        error={error}
      >
        <Field label="Robot name">
          <Input
            autoFocus
            placeholder="Robot name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={FORM_NAME_MAX_LENGTH}
          />
        </Field>
        <Field label="Description">
          <Input
            placeholder="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={FORM_DESCRIPTION_MAX_LENGTH}
          />
        </Field>
      </FormDialog>

      <FormDialog
        open={tokenOpen}
        onClose={closeTokenDialog}
        eyebrow="Robots"
        title={selectedRobot ? `Create token for ${selectedRobot.name}` : "Create robot token"}
        description="The raw secret is shown once after creation."
        onSubmit={createRobotToken}
        submitLabel="Create token"
        submitPendingLabel="Creating..."
        pending={pending}
        disabled={!canCreateRobotToken}
        error={error}
      >
        <Field label="Token name">
          <Input
            autoFocus
            placeholder="default"
            value={tokenName}
            onChange={(event) => setTokenName(event.target.value)}
            required
            maxLength={FORM_NAME_MAX_LENGTH}
          />
        </Field>
      </FormDialog>
    </>
  );
}
