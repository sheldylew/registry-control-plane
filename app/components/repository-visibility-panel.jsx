"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import Alert from "@/app/components/ui/alert";
import Badge from "@/app/components/ui/badge";
import Switch from "@/app/components/ui/switch";
import { readApiErrorDetail } from "@/app/lib/user-form";

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

export default function RepositoryVisibilityPanel({ repositoryName, initialVisibility }) {
  const router = useRouter();
  const [isPublic, setIsPublic] = useState(initialVisibility === "public");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function updateVisibility(nextPublic) {
    setIsPublic(nextPublic);
    setError("");
    setSaving(true);

    try {
      const response = await fetch("/api/admin/repositories/visibility", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": readCookie("rcr_csrf"),
        },
        body: JSON.stringify({
          repository_name: repositoryName,
          visibility: nextPublic ? "public" : "private",
        }),
      });

      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        setIsPublic(initialVisibility === "public");
        setError(readApiErrorDetail(payload, "Could not update repository visibility."));
        return;
      }

      setIsPublic(payload.repository.visibility === "public");
      router.refresh();
    } catch {
      setIsPublic(initialVisibility === "public");
      setError("Could not update repository visibility.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="w-full rounded-lg border border-white/10 bg-slate-950/60 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-white">Repository visibility</p>
          <p className="mt-1 text-sm text-slate-400">
            Public repositories allow anonymous pull-only access. Private repositories require authenticated access.
          </p>
        </div>
        <Badge tone={isPublic ? "emerald" : "slate"} dot>
          {isPublic ? "Public read" : "Private"}
        </Badge>
      </div>
      <div className="mt-4">
        <Switch
          checked={isPublic}
          onChange={updateVisibility}
          loading={saving}
          label={isPublic ? "Public read enabled" : "Private repository"}
          description={isPublic ? "Anonymous pull tokens are allowed." : "All pulls require authenticated access."}
          align="start"
        />
      </div>
      {error ? <Alert tone="rose" className="mt-3">{error}</Alert> : null}
    </div>
  );
}
