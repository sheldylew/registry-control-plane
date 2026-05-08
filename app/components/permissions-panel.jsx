"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Label, Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import { CheckIcon, ChevronUpDownIcon } from "@heroicons/react/20/solid";

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

function CustomListbox({ label, value, options, onChange, disabled = false }) {
  const selected = value || options[0] || { label: "None available", value: "" };

  return (
    <div className="space-y-2">
      <Listbox value={selected} by="value" onChange={onChange} disabled={disabled || options.length === 0}>
        <Label className="block text-sm text-slate-300">{label}</Label>
        <div className="relative">
          <ListboxButton className="grid w-full cursor-default grid-cols-1 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-left text-white outline-none transition hover:border-cyan-400/40 focus-visible:border-cyan-400 focus-visible:ring-2 focus-visible:ring-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-60">
            <span className="col-start-1 row-start-1 truncate pr-7 text-sm font-medium">{selected.label}</span>
            <ChevronUpDownIcon
              aria-hidden="true"
              className="col-start-1 row-start-1 size-5 self-center justify-self-end text-slate-400"
            />
          </ListboxButton>
          <ListboxOptions
            transition
            className="absolute z-10 mt-2 max-h-60 w-full overflow-auto rounded-2xl border border-white/10 bg-slate-950 py-1 text-sm shadow-2xl shadow-slate-950/40 outline-none data-[closed]:data-[leave]:opacity-0 data-[leave]:transition data-[leave]:duration-100 data-[leave]:ease-in"
          >
            {options.map((option) => (
              <ListboxOption
                key={option.value}
                value={option}
                className="group relative cursor-default select-none py-2.5 pl-9 pr-4 text-white data-[focus]:bg-cyan-400 data-[focus]:text-slate-950 data-[focus]:outline-none"
              >
                <span className="block truncate font-normal group-data-[selected]:font-semibold">{option.label}</span>
                <span className="absolute inset-y-0 left-0 hidden items-center pl-2 text-cyan-300 group-data-[focus]:text-slate-950 group-data-[selected]:flex">
                  <CheckIcon aria-hidden="true" className="size-5" />
                </span>
              </ListboxOption>
            ))}
          </ListboxOptions>
        </div>
      </Listbox>
    </div>
  );
}

function PermissionCheckbox({ id, label, description, checked, onChange }) {
  return (
    <div className="flex gap-3 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3">
      <div className="flex h-6 shrink-0 items-center">
        <div className="group grid size-4 grid-cols-1">
          <input
            id={id}
            name={id}
            type="checkbox"
            checked={checked}
            onChange={(event) => onChange(event.target.checked)}
            aria-describedby={`${id}-description`}
            className="col-start-1 row-start-1 appearance-none rounded-sm border border-white/10 bg-white/5 checked:border-cyan-400 checked:bg-cyan-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400 disabled:border-white/5 disabled:bg-white/10 disabled:checked:bg-white/10 forced-colors:appearance-auto"
          />
          <svg
            fill="none"
            viewBox="0 0 14 14"
            className="pointer-events-none col-start-1 row-start-1 size-3.5 self-center justify-self-center stroke-slate-950 group-has-disabled:stroke-white/25"
          >
            <path
              d="M3 8L6 11L11 3.5"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="opacity-0 group-has-checked:opacity-100"
            />
          </svg>
        </div>
      </div>
      <div className="text-sm leading-6">
        <label htmlFor={id} className="font-medium text-white">
          {label}
        </label>{" "}
        <span id={`${id}-description`} className="text-slate-400">
          <span className="sr-only">{label} </span>
          {description}
        </span>
      </div>
    </div>
  );
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
  const subjectTypeOptions = [
    { value: "user", label: "User" },
    { value: "robot", label: "Robot" },
  ];
  const selectedSubjectType = subjectTypeOptions.find((option) => option.value === subjectType) || subjectTypeOptions[0];
  const subjectListboxOptions = subjectOptions.map((subject) => ({
    value: String(subject.id),
    label: subjectType === "user" ? subject.username : subject.name,
  }));
  const selectedSubject = subjectListboxOptions.find((option) => option.value === subjectId) || subjectListboxOptions[0];

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
          <CustomListbox
            label="Subject type"
            value={selectedSubjectType}
            options={subjectTypeOptions}
            onChange={(option) => resetForm(option.value)}
          />
          <CustomListbox
            label="Subject"
            value={selectedSubject}
            options={subjectListboxOptions}
            onChange={(option) => setSubjectId(option.value)}
          />
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

        <fieldset className="mt-4">
          <legend className="sr-only">Repository access</legend>
          <div className="grid gap-3 md:grid-cols-3">
            {[
              ["permission-pull", "Pull", "read images from matches.", canPull, setCanPull],
              ["permission-push", "Push", "write images to matches.", canPush, setCanPush],
              ["permission-delete", "Delete tag", "remove matching tags.", canDelete, setCanDelete],
            ].map(([id, label, description, value, setter]) => (
              <PermissionCheckbox
                id={id}
                key={label}
                label={label}
                description={description}
                checked={value}
                onChange={setter}
              />
            ))}
          </div>
        </fieldset>

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
