"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { FORM_NAME_MAX_LENGTH, hasNonEmptyValue, normalizeTextInput, readApiErrorDetail } from "@/app/lib/user-form";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

function subjectLabel(permission) {
  return permission.subject_type === "user" ? `User: ${permission.subject_name}` : `Robot: ${permission.subject_name}`;
}

export default function PermissionsPanel({ initialUsers, initialRobots, initialPermissions }) {
  const router = useRouter();
  const [subjectType, setSubjectType] = useState("user");
  const [subjectId, setSubjectId] = useState(initialUsers[0]?.id?.toString() || "");
  const [repositoryPattern, setRepositoryPattern] = useState("");
  const [canPull, setCanPull] = useState(true);
  const [canPush, setCanPush] = useState(false);
  const [canDelete, setCanDelete] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const hasValidRepositoryPattern = hasNonEmptyValue(repositoryPattern);
  const canSavePermission =
    Boolean(subjectId) &&
    hasValidRepositoryPattern &&
    (canPull || canPush || canDelete);

  const subjectOptions = useMemo(
    () => (subjectType === "user" ? initialUsers : initialRobots),
    [initialRobots, initialUsers, subjectType],
  );

  function resetForm(nextType = subjectType) {
    const nextOptions = nextType === "user" ? initialUsers : initialRobots;
    setSubjectType(nextType);
    setSubjectId(nextOptions[0]?.id?.toString() || "");
    setRepositoryPattern("");
    setCanPull(true);
    setCanPush(false);
    setCanDelete(false);
    setEditingId(null);
  }

  async function savePermission(event) {
    event.preventDefault();
    const normalizedPattern = normalizeTextInput(repositoryPattern);
    if (!normalizedPattern) {
      setError("Repository pattern is required.");
      return;
    }
    if (!canPull && !canPush && !canDelete) {
      setError("Select at least one permission.");
      return;
    }
    setError("");

    const response = await fetch("/api/admin/permissions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({
        subject_type: subjectType,
        subject_id: Number(subjectId),
        repository_pattern: normalizedPattern,
        can_pull: canPull,
        can_push: canPush,
        can_delete: canDelete,
      }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(readApiErrorDetail(payload, "Could not save permission."));
      return;
    }

    resetForm(subjectType);
    router.refresh();
  }

  async function removePermission(permissionId) {
    setError("");
    const response = await fetch(`/api/admin/permissions/${permissionId}/delete`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Could not delete permission.");
      return;
    }
    if (editingId === permissionId) {
      resetForm(subjectType);
    }
    router.refresh();
  }

  function beginEdit(permission) {
    setEditingId(permission.id);
    setSubjectType(permission.subject_type);
    setSubjectId(String(permission.subject_id));
    setRepositoryPattern(permission.repository_pattern);
    setCanPull(permission.can_pull);
    setCanPush(permission.can_push);
    setCanDelete(permission.can_delete);
    setError("");
  }

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <h2 className="text-xl font-semibold text-white">Repository permissions</h2>
        <p className="mt-3 text-sm leading-7 text-slate-300">
          Grant pull, push, and tag-delete access to users and robot accounts by repository pattern.
        </p>
      </div>

      <form onSubmit={savePermission} className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <div className="flex items-center justify-between gap-4">
          <h3 className="text-lg font-semibold text-white">{editingId ? "Edit permission" : "Add permission"}</h3>
          {editingId ? (
            <button
              type="button"
              onClick={() => resetForm(subjectType)}
              className="rounded-full border border-white/10 px-3 py-1 text-xs font-semibold text-slate-200"
            >
              Cancel edit
            </button>
          ) : null}
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="space-y-2">
            <span className="text-sm text-slate-300">Subject type</span>
            <select
              value={subjectType}
              onChange={(event) => resetForm(event.target.value)}
              required
              className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
            >
              <option value="user">User</option>
              <option value="robot">Robot</option>
            </select>
          </label>
          <label className="space-y-2">
            <span className="text-sm text-slate-300">Subject</span>
            <select
              value={subjectId}
              onChange={(event) => setSubjectId(event.target.value)}
              required
              className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
            >
              {subjectOptions.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subjectType === "user" ? subject.username : subject.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 md:col-span-2">
            <span className="text-sm text-slate-300">Repository pattern</span>
            <input
              value={repositoryPattern}
              onChange={(event) => setRepositoryPattern(event.target.value)}
              placeholder="sheldylew/*"
              required
              maxLength={FORM_NAME_MAX_LENGTH}
              className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
            />
          </label>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {[
            ["Pull", canPull, setCanPull],
            ["Push", canPush, setCanPush],
            ["Delete tag", canDelete, setCanDelete],
          ].map(([label, value, setter]) => (
            <label
              key={label}
              className="flex items-center gap-3 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-200"
            >
              <input
                type="checkbox"
                checked={value}
                onChange={(event) => setter(event.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>

        {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}

        <button
          disabled={!canSavePermission}
          className="mt-5 rounded-xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {editingId ? "Save permission" : "Add permission"}
        </button>
      </form>

      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <h3 className="text-lg font-semibold text-white">Current permissions</h3>
        <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
          <table className="min-w-full divide-y divide-white/10 text-sm">
            <thead className="bg-white/5 text-slate-300">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Subject</th>
                <th className="px-4 py-3 text-left font-medium">Pattern</th>
                <th className="px-4 py-3 text-left font-medium">Pull</th>
                <th className="px-4 py-3 text-left font-medium">Push</th>
                <th className="px-4 py-3 text-left font-medium">Delete tag</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {initialPermissions.map((permission) => (
                <tr key={permission.id}>
                  <td className="px-4 py-3 text-white">{subjectLabel(permission)}</td>
                  <td className="px-4 py-3 font-mono text-slate-300">{permission.repository_pattern}</td>
                  <td className="px-4 py-3 text-slate-300">{permission.can_pull ? "Yes" : "No"}</td>
                  <td className="px-4 py-3 text-slate-300">{permission.can_push ? "Yes" : "No"}</td>
                  <td className="px-4 py-3 text-slate-300">{permission.can_delete ? "Yes" : "No"}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => beginEdit(permission)}
                        className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-100"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => removePermission(permission.id)}
                        className="rounded-full border border-rose-400/30 bg-rose-400/10 px-3 py-1 text-xs font-semibold text-rose-100"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!initialPermissions.length ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-300">
                    No explicit repository permissions are configured yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
