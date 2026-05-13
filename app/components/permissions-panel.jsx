"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Label, Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import { CheckIcon, ChevronUpDownIcon } from "@heroicons/react/20/solid";

import ActionMenu from "@/app/components/ui/action-menu";
import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import FormDialog from "@/app/components/ui/form-dialog";
import { Input } from "@/app/components/ui/form";
import { MobileCollapsiblePanel, Panel, PanelHeader } from "@/app/components/ui/panel";
import Pagination from "@/app/components/ui/pagination";
import Switch from "@/app/components/ui/switch";
import {
  MobileCardList,
  MobileDisclosureCard,
  MobileField,
  Table,
  TableBody,
  TableHead,
  TableShell,
} from "@/app/components/ui/table";
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
          <ListboxButton className="grid w-full cursor-default grid-cols-1 rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-left text-white outline-none transition hover:border-cyan-400/40 focus-visible:border-cyan-400 focus-visible:ring-2 focus-visible:ring-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-60">
            <span className="col-start-1 row-start-1 truncate pr-7 text-sm font-medium">{selected.label}</span>
            <ChevronUpDownIcon
              aria-hidden="true"
              className="col-start-1 row-start-1 size-5 self-center justify-self-end text-slate-400"
            />
          </ListboxButton>
          <ListboxOptions
            transition
            className="absolute z-10 mt-2 max-h-60 w-full overflow-auto rounded-lg border border-white/10 bg-slate-950 py-1 text-sm shadow-2xl shadow-slate-950/40 outline-none data-[closed]:data-[leave]:opacity-0 data-[leave]:transition data-[leave]:duration-100 data-[leave]:ease-in"
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

export default function PermissionsPanel({ initialUsers, initialRobots, initialPermissions, pagination }) {
  const router = useRouter();
  const [subjectType, setSubjectType] = useState("user");
  const [subjectId, setSubjectId] = useState(initialUsers[0]?.id?.toString() || "");
  const [repositoryPattern, setRepositoryPattern] = useState("");
  const [canPull, setCanPull] = useState(true);
  const [canPush, setCanPush] = useState(false);
  const [canDelete, setCanDelete] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [savePending, setSavePending] = useState(false);
  const [deletePendingId, setDeletePendingId] = useState(null);
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

  function openCreateDialog() {
    resetForm("user");
    setError("");
    setDialogOpen(true);
  }

  function closeDialog() {
    if (savePending) {
      return;
    }
    setDialogOpen(false);
    setError("");
    resetForm(subjectType);
  }

  function buildPageHref(page) {
    if (page <= 1) {
      return "/admin/permissions";
    }
    const params = new URLSearchParams();
    params.set("page", String(page));
    return `/admin/permissions?${params.toString()}`;
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
    setDialogOpen(true);
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
    setSavePending(true);

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
      setSavePending(false);
      return;
    }

    setSavePending(false);
    closeDialog();
    router.refresh();
  }

  async function removePermission(permissionId) {
    setError("");
    setDeletePendingId(permissionId);
    const response = await fetch(`/api/admin/permissions/${permissionId}/delete`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Could not delete permission.");
      setDeletePendingId(null);
      return;
    }
    if (editingId === permissionId) {
      closeDialog();
    }
    setDeletePendingId(null);
    router.refresh();
  }

  return (
    <>
      <div className="space-y-6">
        <Panel className="p-4 sm:p-6">
          <PanelHeader
            title="Repository permissions"
            description="Inspect the current access map first, then open focused add or edit flows when a change is needed."
            action={(
              <Button type="button" onClick={openCreateDialog} size="lg" className="w-full sm:w-auto">
                Add permission
              </Button>
            )}
          />
          <div className="mt-6 flex flex-wrap gap-3">
            <Badge tone="cyan">{pagination.total} rules</Badge>
            <Badge tone="slate">{initialUsers.length} users</Badge>
            <Badge tone="slate">{initialRobots.length} robots</Badge>
          </div>
          {error ? <Alert tone="rose" className="mt-6">{error}</Alert> : null}
        </Panel>

        <MobileCollapsiblePanel className="p-4 sm:p-6" title="Current permissions" summaryMeta={`${pagination.total} rules`}>
          <PanelHeader title="Current permissions" />
          <div className="mt-4">
            <TableShell
              mobileCards={(
                <MobileCardList>
                  {initialPermissions.map((permission) => (
                    <MobileDisclosureCard
                      key={permission.id}
                      summary={(
                        <>
                          <p className="text-base font-semibold text-white">{subjectLabel(permission)}</p>
                          <p className="mt-1 break-all font-mono text-xs text-slate-400">{permission.repository_pattern}</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {permission.can_pull ? <Badge tone="emerald">Pull</Badge> : null}
                            {permission.can_push ? <Badge tone="cyan">Push</Badge> : null}
                            {permission.can_delete ? <Badge tone="amber">Delete tag</Badge> : null}
                          </div>
                        </>
                      )}
                    >
                      <div className="flex justify-end">
                        <ActionMenu
                          items={[
                            {
                              label: "Edit",
                              onSelect: () => beginEdit(permission),
                            },
                            {
                              label: deletePendingId === permission.id ? "Deleting..." : "Delete permission",
                              onSelect: () => removePermission(permission.id),
                              loading: deletePendingId === permission.id,
                            },
                          ]}
                          label={`Actions for ${subjectLabel(permission)}`}
                        />
                      </div>
                      <dl className="mt-4 grid gap-4">
                        <MobileField label="Access">
                          <div className="flex flex-wrap gap-2">
                            <Badge tone={permission.can_pull ? "emerald" : "slate"}>{permission.can_pull ? "Pull" : "No pull"}</Badge>
                            <Badge tone={permission.can_push ? "cyan" : "slate"}>{permission.can_push ? "Push" : "No push"}</Badge>
                            <Badge tone={permission.can_delete ? "amber" : "slate"}>{permission.can_delete ? "Delete tag" : "No delete"}</Badge>
                          </div>
                        </MobileField>
                      </dl>
                    </MobileDisclosureCard>
                  ))}
                </MobileCardList>
              )}
            >
              <Table>
                <TableHead>
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Subject</th>
                    <th className="px-4 py-3 text-left font-medium">Pattern</th>
                    <th className="px-4 py-3 text-left font-medium">Access</th>
                    <th className="px-4 py-3 text-right font-medium">Actions</th>
                  </tr>
                </TableHead>
                <TableBody>
                  {initialPermissions.length ? initialPermissions.map((permission) => (
                    <tr key={permission.id}>
                      <td className="px-4 py-3 text-white">{subjectLabel(permission)}</td>
                      <td className="px-4 py-3 font-mono text-slate-300">{permission.repository_pattern}</td>
                      <td className="px-4 py-3 text-slate-300">
                        <div className="flex flex-wrap gap-2">
                          <Badge tone={permission.can_pull ? "emerald" : "slate"}>{permission.can_pull ? "Pull" : "No pull"}</Badge>
                          <Badge tone={permission.can_push ? "cyan" : "slate"}>{permission.can_push ? "Push" : "No push"}</Badge>
                          <Badge tone={permission.can_delete ? "amber" : "slate"}>{permission.can_delete ? "Delete tag" : "No delete"}</Badge>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            type="button"
                            onClick={() => beginEdit(permission)}
                            variant="soft"
                            size="xs"
                          >
                            Edit
                          </Button>
                          <ActionMenu
                            items={[
                              {
                                label: deletePendingId === permission.id ? "Deleting..." : "Delete permission",
                                onSelect: () => removePermission(permission.id),
                                loading: deletePendingId === permission.id,
                              },
                            ]}
                            label={`Actions for ${subjectLabel(permission)}`}
                          />
                        </div>
                      </td>
                    </tr>
                  )) : null}
                </TableBody>
              </Table>
            </TableShell>
          </div>
          {!initialPermissions.length ? (
            <div className="mt-6">
              <EmptyState
                title="No repository permissions"
                description="Add a permission to grant a user or robot account access to matching repositories."
                action={(
                  <Button type="button" onClick={openCreateDialog}>
                    Add permission
                  </Button>
                )}
              />
            </div>
          ) : null}
          <Pagination
            page={pagination.page}
            pageSize={pagination.page_size}
            total={pagination.total}
            label="rules"
            hrefForPage={buildPageHref}
          />
        </MobileCollapsiblePanel>
      </div>

      <FormDialog
        open={dialogOpen}
        onClose={closeDialog}
        eyebrow="Permissions"
        title={editingId ? "Edit permission" : "Add permission"}
        description="Keep the page itself in presentation mode and use a focused dialog for access changes."
        onSubmit={savePermission}
        submitLabel={editingId ? "Save permission" : "Add permission"}
        submitPendingLabel={editingId ? "Saving..." : "Adding..."}
        pending={savePending}
        disabled={!canSavePermission}
        error={error}
        maxWidth="max-w-2xl"
      >
        <div className="grid gap-4 md:grid-cols-2">
          <CustomListbox
            label="Subject type"
            value={selectedSubjectType}
            options={subjectTypeOptions}
            disabled={savePending}
            onChange={(option) => {
              resetForm(option.value);
              setDialogOpen(true);
            }}
          />
          <CustomListbox
            label="Subject"
            value={selectedSubject}
            options={subjectListboxOptions}
            disabled={savePending}
            onChange={(option) => setSubjectId(option.value)}
          />
          <label className="space-y-2 md:col-span-2">
            <span className="text-sm text-slate-300">Repository pattern</span>
            <Input
              value={repositoryPattern}
              onChange={(event) => setRepositoryPattern(event.target.value)}
              placeholder="sheldylew/*"
              required
              maxLength={FORM_NAME_MAX_LENGTH}
            />
          </label>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-white/10 bg-slate-950 px-4 py-3">
            <Switch
              checked={canPull}
              onChange={setCanPull}
              label="Pull"
              description="Allow image reads from matching repositories."
              align="start"
            />
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950 px-4 py-3">
            <Switch
              checked={canPush}
              onChange={setCanPush}
              label="Push"
              description="Allow writes to matching repositories."
              align="start"
            />
          </div>
          <div className="rounded-lg border border-white/10 bg-slate-950 px-4 py-3">
            <Switch
              checked={canDelete}
              onChange={setCanDelete}
              label="Delete tag"
              description="Allow tag delete operations."
              align="start"
            />
          </div>
        </div>
      </FormDialog>
    </>
  );
}
