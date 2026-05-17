"use client";

import { useState } from "react";
import { InformationCircleIcon } from "@heroicons/react/20/solid";

import Button from "@/app/components/ui/button";
import DetailList from "@/app/components/ui/detail-list";
import Dialog from "@/app/components/ui/dialog";

function formatBuildTimestamp(value) {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const pad = (part) => String(part).padStart(2, "0");
  return [
    parsed.getUTCFullYear(),
    pad(parsed.getUTCMonth() + 1),
    pad(parsed.getUTCDate()),
  ].join("-") + ` ${pad(parsed.getUTCHours())}:${pad(parsed.getUTCMinutes())}:${pad(parsed.getUTCSeconds())}Z`;
}

function buildInfoItems(build) {
  return [
    {
      label: "Version",
      value: <code className="break-all text-sm text-white">{build?.version || "dev"}</code>,
    },
    {
      label: "Revision",
      value: <code className="break-all text-sm text-white">{build?.revision || "dev"}</code>,
    },
    {
      label: "Built at",
      value: <code className="break-all text-sm text-white">{formatBuildTimestamp(build?.built_at)}</code>,
    },
    {
      label: "Image tag",
      value: <code className="break-all text-sm text-white">{build?.image_tag || "Unavailable"}</code>,
    },
  ];
}

export default function BuildInfoDialog({ build }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        onClick={() => setOpen(true)}
        variant="secondary"
        size="iconLg"
        aria-label="Show build information"
        title="Show build information"
      >
        <InformationCircleIcon className="h-5 w-5" aria-hidden="true" />
      </Button>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        eyebrow="Settings"
        title="Build information"
        maxWidth="max-w-5xl"
      >
        <p className="text-sm leading-7 text-slate-300">
          Read-only metadata baked into the running API and web images.
        </p>
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">API image</h3>
            <DetailList columns={1} compact items={buildInfoItems(build?.api || build)} />
          </div>
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Web image</h3>
            <DetailList columns={1} compact items={buildInfoItems(build?.web)} />
          </div>
        </div>
      </Dialog>
    </>
  );
}
