"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowPathIcon } from "@heroicons/react/20/solid";

import Alert from "@/app/components/ui/alert";
import Button from "@/app/components/ui/button";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function InboxRetryButton({ entryId, className = "" }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function onRetry() {
    setPending(true);
    setError("");

    const response = await fetch(`/api/admin/maintenance/inbox/${entryId}/retry`, {
      method: "POST",
      headers: {
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body.detail || "Unable to retry inbox entry.");
      setPending(false);
      return;
    }

    setPending(false);
    router.refresh();
  }

  return (
    <div className={className}>
      {error ? <Alert tone="rose" className="mb-3">{error}</Alert> : null}
      <Button
        type="button"
        onClick={onRetry}
        disabled={pending}
        loading={pending}
        variant="soft"
        size="sm"
        className="w-full sm:w-auto"
      >
        {pending ? null : <ArrowPathIcon className="h-4 w-4" />}
        {pending ? "Retrying..." : "Retry"}
      </Button>
    </div>
  );
}
