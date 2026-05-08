"use client";

import { useRouter } from "next/navigation";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function LogoutButton() {
  const router = useRouter();

  async function onLogout() {
    const csrf = readCookie("rcr_csrf");
    await fetch("/api/session/logout", {
      method: "POST",
      headers: {
        "X-CSRF-Token": csrf,
      },
    });
    router.push("/login");
    router.refresh();
  }

  return (
    <button
      onClick={onLogout}
      className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/10"
    >
      Log out
    </button>
  );
}
