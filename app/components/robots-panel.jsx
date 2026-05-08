"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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
      <form
        onSubmit={createRobot}
        className="rounded-3xl border border-white/10 bg-slate-900/80 p-6"
      >
        <h2 className="text-xl font-semibold text-white">Robot accounts</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto]">
          <input
            placeholder="Robot name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={FORM_NAME_MAX_LENGTH}
            className="rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
          />
          <input
            placeholder="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={FORM_DESCRIPTION_MAX_LENGTH}
            className="rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
          />
          <button
            disabled={pending || !canCreateRobot}
            className="rounded-xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? "Creating..." : "Create robot"}
          </button>
        </div>
        {latestToken ? (
          <div className="mt-4 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-emerald-200">
              Robot token
            </p>
            <p className="mt-2 break-all font-mono text-sm text-white">{latestToken}</p>
          </div>
        ) : null}
        {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}
      </form>

      <div className="space-y-4">
        {initialRobots.map((robot) => (
          <article
            key={robot.id}
            className="rounded-3xl border border-white/10 bg-slate-900/80 p-6"
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-semibold text-white">{robot.name}</h3>
                  <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs uppercase tracking-[0.16em] text-slate-300">
                    {robot.is_active ? "Active" : "Disabled"}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-300">{robot.description || "No description."}</p>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {robot.is_active ? (
                  <>
                    <button
                      onClick={() => createRobotToken(robot.id)}
                      className="inline-flex h-8 items-center rounded-full border border-white/10 bg-white/5 px-3 text-xs font-semibold text-white"
                    >
                      Create token
                    </button>
                    <button
                      onClick={() => disableRobot(robot.id)}
                      className="inline-flex h-8 items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-3 text-xs font-semibold text-amber-100"
                    >
                      Disable
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => enableRobot(robot.id)}
                    className="inline-flex h-8 items-center rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 text-xs font-semibold text-emerald-100"
                  >
                    Enable
                  </button>
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
                  className="flex items-center justify-between gap-4 rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-slate-300"
                >
                  <div>
                    <span>{token.name} • prefix {token.token_prefix}</span>
                    {token.revoked_at ? (
                      <span className="ml-3 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-xs uppercase tracking-[0.16em] text-slate-400">
                        Revoked
                      </span>
                    ) : null}
                  </div>
                  {!token.revoked_at ? (
                    <button
                      onClick={() => revokeRobotToken(robot.id, token.id)}
                      className="inline-flex h-8 items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-3 text-xs font-semibold text-amber-100"
                    >
                      Revoke
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </div>
  );
}
