"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import Dialog from "@/app/components/ui/dialog";
import Pagination from "@/app/components/ui/pagination";
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
  const hasValidUsername = hasNonEmptyValue(username);
  const hasValidEmail = isValidUserEmail(email);
  const canCreateUser = hasValidUsername && hasValidEmail && isValidPassword(password);

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

  async function disableUser(userId) {
    const response = await fetch(`/api/admin/users/${userId}/disable`, {
      method: "POST",
      headers: { "X-CSRF-Token": readCookie("rcr_csrf") },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail || "Could not disable user.");
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
      <div className="rounded-3xl border border-white/10 bg-slate-900/80 p-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-xl font-semibold text-white">Users</h2>
          <button
            type="button"
            onClick={openDialog}
            className="rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
          >
            Create user
          </button>
        </div>
        <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
          <table className="min-w-full divide-y divide-white/10 text-sm">
            <thead className="bg-white/5 text-slate-300">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Username</th>
                <th className="px-4 py-3 text-left font-medium">Email</th>
                <th className="px-4 py-3 text-left font-medium">Role</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {initialUsers.map((user) => (
                <tr key={user.id}>
                  <td className="px-4 py-3 text-white">{user.username}</td>
                  <td className="px-4 py-3 text-slate-300">{user.email}</td>
                  <td className="px-4 py-3 text-slate-300">
                    {user.is_admin ? "Admin" : "User"}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {user.is_active ? "Active" : "Disabled"}
                  </td>
                  <td className="px-4 py-3">
                    {user.is_active && user.id !== currentUserId ? (
                      <button
                        onClick={() => disableUser(user.id)}
                        className="rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1 text-xs font-semibold text-amber-100"
                      >
                        Disable
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-6">
          <Pagination
            page={pagination.page}
            pageSize={pagination.page_size}
            total={pagination.total}
            label="users"
            hrefForPage={buildPageHref}
          />
        </div>
      </div>

      <Dialog open={open} onClose={closeDialog} eyebrow="User management" title="Create user">
        <form onSubmit={createUser}>
          <div className="grid gap-4 md:grid-cols-2">
            <input
              autoFocus
              placeholder="Username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              maxLength={FORM_NAME_MAX_LENGTH}
              className="rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
            />
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              maxLength={FORM_EMAIL_MAX_LENGTH}
              pattern="^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$"
              title="Use an address with a full domain, like name@example.com."
              className="rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
              className="rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-white"
            />
            <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={isAdmin}
                onChange={(event) => setIsAdmin(event.target.checked)}
              />
              Admin user
            </label>
          </div>
          {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}
          <div className="mt-5 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={closeDialog}
              disabled={pending}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-white/20 hover:text-white disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={pending || !canCreateUser}
              className="rounded-full bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pending ? "Creating..." : "Create user"}
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
