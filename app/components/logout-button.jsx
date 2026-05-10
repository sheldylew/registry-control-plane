"use client";

import { useState } from "react";
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
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onLogout() {
    setError("");
    setPending(true);
    const csrf = readCookie("rcr_csrf");
    try {
      const response = await fetch("/api/session/logout", {
        method: "POST",
        headers: {
          "X-CSRF-Token": csrf,
        },
      });
      if (!response.ok) {
        throw new Error("Logout failed.");
      }
      router.push("/");
      router.refresh();
    } catch {
      setError(
        "Logout could not be confirmed. If you are offline, close this browser or clear site data for this registry to remove the local session.",
      );
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <Button
        type="button"
        onClick={onLogout}
        variant="secondary"
        disabled={pending}
        loading={pending}
      >
        {pending ? "Logging out..." : "Log out"}
      </Button>
      {error ? (
        <p className="max-w-xs text-right text-xs leading-5 text-amber-200">
          {error}
        </p>
      ) : null}
    </div>
  );
}
