"use client";

import { useRouter } from "next/navigation";

import Button from "@/app/components/ui/button";

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
    <Button
      type="button"
      onClick={onLogout}
      variant="secondary"
    >
      Log out
    </Button>
  );
}
