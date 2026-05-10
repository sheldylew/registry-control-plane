"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

import ActionMenu from "@/app/components/ui/action-menu";
import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import EmptyState from "@/app/components/ui/empty-state";
import FormDialog from "@/app/components/ui/form-dialog";
import { Field, Input } from "@/app/components/ui/form";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import Pagination from "@/app/components/ui/pagination";
import Switch from "@/app/components/ui/switch";
import {
  FORM_EMAIL_MAX_LENGTH,
  FORM_NAME_MAX_LENGTH,
  hasNonEmptyValue,
  isValidPassword,
  isValidUserEmail,
  normalizeTextInput,
  readApiErrorDetail,
} from "@/app/lib/user-form";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function UsersPanel({
  initialUsers,
  currentUserId,
  pagination,
}) {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [statusError, setStatusError] = useState("");
  const [pendingStatusUserId, setPendingStatusUserId] = useState(null);
  const [passwordResetUser, setPasswordResetUser] = useState(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [resetPending, setResetPending] = useState(false);
  const [resetError, setResetError] = useState("");
  const hasValidUsername = hasNonEmptyValue(username);
  const hasValidEmail = isValidUserEmail(email);
  const canCreateUser = hasValidUsername && hasValidEmail && isValidPassword(password);
  const resettingOwnPassword = passwordResetUser?.id === currentUserId;
  const canResetPassword = (
    (!resettingOwnPassword || isValidPassword(currentPassword, 1))
    && isValidPassword(newPassword)
    && newPassword === confirmPassword
  );

  function openDialog() {
    setError("");
    setOpen(true);
  }

  function closeDialog() {
    if (pending) {
      return;
    }
    setOpen(false);
    setError("");
  }

  function resetForm() {
    setUsername("");
    setEmail("");
    setPassword("");
    setIsAdmin(false);
  }

  function openPasswordReset(user) {
    setPasswordResetUser(user);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setResetError("");
  }

  function closePasswordReset() {
    if (resetPending) {
      return;
    }
    setPasswordResetUser(null);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setResetError("");
  }

  async function createUser(event) {
    event.preventDefault();
    const normalizedUsername = normalizeTextInput(username);
    const normalizedEmail = normalizeTextInput(email);

    if (!normalizedUsername) {
      setError("Username is required.");
      return;
    }
    if (!hasValidEmail) {
      setError("Email must include a full domain like name@example.com.");
      return;
    }
    if (!isValidPassword(password)) {
      setError("Password must be at least 8 characters and not only whitespace.");
      return;
    }
    setPending(true);
    setError("");
    const response = await fetch("/api/admin/users", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({
        username: normalizedUsername,
        email: normalizedEmail,
        password,
        is_admin: isAdmin,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(readApiErrorDetail(payload, "Could not create user."));
      setPending(false);
      return;
    }
    resetForm();
    setOpen(false);
    setPending(false);
    router.refresh();
  }

  async function setUserActive(user, nextActive) {
    if (user.id === currentUserId && !nextActive) {
      return;
    }

    setPendingStatusUserId(user.id);
    setStatusError("");
    const response = await fetch(`/api/admin/users/${user.id}/${nextActive ? "enable" : "disable"}`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setStatusError(readApiErrorDetail(payload, `Could not ${nextActive ? "enable" : "disable"} user.`));
      setPendingStatusUserId(null);
      return;
    }
    setPendingStatusUserId(null);
    router.refresh();
  }

  async function resetUserPassword(event) {
    event.preventDefault();
    if (!passwordResetUser) {
      return;
    }
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
    const response = await fetch(`/api/admin/users/${passwordResetUser.id}/password`, {
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

    const resetOwnPassword = passwordResetUser.id === currentUserId;
    setResetPending(false);
    setPasswordResetUser(null);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setResetError("");
    if (resetOwnPassword) {
      router.push("/");
      return;
    }
    router.refresh();
  }

  function buildPageHref(page) {
    if (page <= 1) {
      return "/admin/users";
    }
    const params = new URLSearchParams();
    params.set("page", String(page));
    return `/admin/users?${params.toString()}`;
  }

  return (
    <>
      <Panel className="p-6">
        <PanelHeader
          title="Users"
          description="Review operator identities first, then open focused create, reset, and profile actions when needed."
          action={(
            <Button
              type="button"
              onClick={openDialog}
              size="lg"
            >
              Create user
            </Button>
          )}
        />

        {statusError ? <Alert tone="rose" className="mt-6">{statusError}</Alert> : null}

        <div className="mt-6 overflow-hidden rounded-lg border border-white/10">
          <table className="min-w-full divide-y divide-white/10 text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-[0.16em] text-slate-400">
              <tr>
                <th className="px-4 py-3 text-left font-medium">User</th>
                <th className="px-4 py-3 text-left font-medium">Role</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {initialUsers.length ? initialUsers.map((user) => (
                <tr key={user.id}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Badge tone={user.is_active ? "emerald" : "amber"} dot>
                        {user.is_active ? "Active" : "Disabled"}
                      </Badge>
                      <Link prefetch={false} href={`/admin/users/${user.id}`} className="font-medium text-white transition hover:text-cyan-200">
                        {user.username}
                      </Link>
                    </div>
                    <p className="mt-1 text-slate-400">{user.email}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    <Badge tone={user.is_admin ? "cyan" : "slate"}>
                      {user.is_admin ? "Admin" : "User"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Switch
                      checked={user.is_active}
                      onChange={(nextActive) => setUserActive(user, nextActive)}
                      disabled={pendingStatusUserId === user.id || (user.id === currentUserId && user.is_active)}
                      srLabel={`Set ${user.username} ${user.is_active ? "inactive" : "active"}`}
                      label={user.is_active ? "Enabled" : "Disabled"}
                      description={user.id === currentUserId ? "Current operator" : "Access toggle"}
                      align="start"
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        as={Link}
                        href={`/admin/users/${user.id}`}
                        prefetch={false}
                        variant="soft"
                        size="xs"
                      >
                        View profile
                      </Button>
                      <ActionMenu
                        items={[
                          {
                            label: "Reset password",
                            onSelect: () => openPasswordReset(user),
                          },
                        ]}
                        label={`Actions for ${user.username}`}
                      />
                    </div>
                  </td>
                </tr>
              )) : null}
            </tbody>
          </table>
        </div>
        {!initialUsers.length ? (
          <div className="mt-6">
            <EmptyState
              title="No users found"
              description="Create the first operator identity for this registry control plane."
              action={(
                <Button type="button" onClick={openDialog}>
                  Create user
                </Button>
              )}
            />
          </div>
        ) : null}
        <div className="mt-6">
          <Pagination
            page={pagination.page}
            pageSize={pagination.page_size}
            total={pagination.total}
            label="users"
            hrefForPage={buildPageHref}
          />
        </div>
      </Panel>

      <FormDialog
        open={open}
        onClose={closeDialog}
        eyebrow="User management"
        title="Create user"
        description="Create the identity first, then manage its profile and password from the detail view."
        onSubmit={createUser}
        submitLabel="Create user"
        submitPendingLabel="Creating..."
        pending={pending}
        disabled={!canCreateUser}
        error={error}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Username">
            <Input
              autoFocus
              placeholder="Username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              maxLength={FORM_NAME_MAX_LENGTH}
            />
          </Field>
          <Field label="Email">
            <Input
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              maxLength={FORM_EMAIL_MAX_LENGTH}
              pattern="^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$"
              title="Use an address with a full domain, like name@example.com."
            />
          </Field>
          <Field label="Password">
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
            />
          </Field>
          <div className="rounded-md border border-white/10 bg-slate-950 px-3 py-3">
            <Switch
              checked={isAdmin}
              onChange={setIsAdmin}
              label={isAdmin ? "Admin access enabled" : "Standard user"}
              description="Admin users can manage identities, permissions, and maintenance."
              align="start"
            />
          </div>
        </div>
      </FormDialog>

      <FormDialog
        open={Boolean(passwordResetUser)}
        onClose={closePasswordReset}
        eyebrow="User management"
        title={`Reset ${passwordResetUser?.username ?? "user"} password`}
        description="Use a focused reset flow instead of editing credentials inline."
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
        {passwordResetUser?.id === currentUserId ? (
          <Alert tone="amber">
            Resetting your own password signs out this browser session.
          </Alert>
        ) : null}
      </FormDialog>
    </>
  );
}
