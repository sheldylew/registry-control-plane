"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import RepoDeletePanel from "@/app/components/repo-delete-panel";
import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import { Input } from "@/app/components/ui/form";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
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
  const [latestToken, setLatestToken] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const canCreateRobot = hasNonEmptyValue(name);

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
    router.refresh();
  }

  async function createRobotToken(robotId) {
    setError("");
    const response = await fetch(`/api/admin/robots/${robotId}/tokens`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({ name: "default" }),
    });
    const payload = await response.json();
    if (response.ok) {
      setLatestToken(payload.raw_token);
      router.refresh();
      return;
    }
    setError(payload.detail || "Could not create robot token.");
  }

  async function revokeRobotToken(robotId, tokenId) {
    setError("");
    const response = await fetch(`/api/admin/robots/${robotId}/tokens/${tokenId}/revoke`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Could not revoke robot token.");
      return;
    }
    router.refresh();
  }

  async function disableRobot(robotId) {
    setError("");
    const response = await fetch(`/api/admin/robots/${robotId}/disable`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Could not disable robot.");
      return;
    }
    router.refresh();
  }

  async function enableRobot(robotId) {
    setError("");
    const response = await fetch(`/api/admin/robots/${robotId}/enable`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Could not enable robot.");
      return;
    }
    router.refresh();
  }

  return (
    <div className="space-y-6">
      <Panel as="form" onSubmit={createRobot} className="p-6">
        <PanelHeader title="Robot accounts" description="Create automation identities and issue scoped registry tokens." />
        <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto]">
          <Input
            placeholder="Robot name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={FORM_NAME_MAX_LENGTH}
          />
          <Input
            placeholder="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={FORM_DESCRIPTION_MAX_LENGTH}
          />
          <Button
            disabled={pending || !canCreateRobot}
            size="lg"
          >
            {pending ? "Creating..." : "Create robot"}
          </Button>
        </div>
        {latestToken ? (
          <Alert tone="emerald" className="mt-4">
            <Badge tone="emerald">Robot token</Badge>
            <p className="mt-2 break-all font-mono text-sm text-white">{latestToken}</p>
          </Alert>
        ) : null}
        {error ? <Alert tone="rose" className="mt-4">{error}</Alert> : null}
      </Panel>

      <div className="space-y-4">
        {initialRobots.length ? initialRobots.map((robot) => (
          <Panel
            as="article"
            key={robot.id}
            className="p-6"
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-semibold text-white">{robot.name}</h3>
                  <Badge tone={robot.is_active ? "emerald" : "amber"} dot>
                    {robot.is_active ? "Active" : "Disabled"}
                  </Badge>
                </div>
                <p className="mt-2 text-sm text-slate-300">{robot.description || "No description."}</p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {robot.is_active ? (
                  <>
                    <Button
                      type="button"
                      onClick={() => createRobotToken(robot.id)}
                      variant="secondary"
                      size="xs"
                    >
                      Create token
                    </Button>
                    <Button
                      type="button"
                      onClick={() => disableRobot(robot.id)}
                      variant="warning"
                      size="xs"
                    >
                      Disable
                    </Button>
                  </>
                ) : (
                  <Button
                    type="button"
                    onClick={() => enableRobot(robot.id)}
                    variant="soft"
                    size="xs"
                  >
                    Enable
                  </Button>
                )}
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
            <ul className="mt-4 space-y-2">
              {robot.tokens.map((token) => (
                <li
                  key={token.id}
                  className="flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-slate-300"
                >
                  <div>
                    <span>{token.name} • prefix {token.token_prefix}</span>
                    {token.revoked_at ? (
                      <span className="ml-3">
                      <Badge>
                        Revoked
                      </Badge>
                      </span>
                    ) : null}
                  </div>
                  {!token.revoked_at ? (
                    <Button
                      type="button"
                      onClick={() => revokeRobotToken(robot.id, token.id)}
                      variant="warning"
                      size="xs"
                    >
                      Revoke
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </Panel>
        )) : (
          <EmptyState
            title="No robot accounts"
            description="Create a robot account when automation needs registry access."
          />
        )}
      </div>
    </div>
  );
}
