"use client";

import { ClipboardDocumentIcon } from "@heroicons/react/24/outline";

import Button from "@/app/components/ui/button";
import { useToast } from "@/app/components/ui/toast-provider";

function registryRefFromOrigin(origin) {
  try {
    const parsed = new URL(origin);
    const path = parsed.pathname.replace(/\/$/, "");
    return `${parsed.host}${path}`;
  } catch {
    return origin.replace(/^https?:\/\//, "").replace(/\/$/, "");
  }
}

function buildDockerPullCommand(origin, repo, tag) {
  return `docker pull ${registryRefFromOrigin(origin)}/${repo}:${tag}`;
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const input = document.createElement("textarea");
  input.value = value;
  input.setAttribute("readonly", "");
  input.style.position = "absolute";
  input.style.left = "-9999px";
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  document.body.removeChild(input);
}

export default function TagCopyButton({
  publicRegistryOrigin,
  repositoryName,
  tag,
  size = "iconMd",
  className = "",
  label = "",
}) {
  const { showToast } = useToast();

  async function onCopy() {
    const command = buildDockerPullCommand(publicRegistryOrigin, repositoryName, tag);
    try {
      await copyText(command);
      showToast({
        title: "Docker pull command copied",
        description: command,
      });
    } catch {
      showToast({
        title: "Copy failed",
        description: "Clipboard access is unavailable in this browser session.",
        tone: "error",
      });
    }
  }

  return (
    <Button
      type="button"
      variant="secondary"
      size={size}
      className={className}
      onClick={onCopy}
      aria-label={`Copy docker pull command for ${repositoryName}:${tag}`}
      title={`Copy docker pull command for ${repositoryName}:${tag}`}
    >
      <ClipboardDocumentIcon className="h-4 w-4" aria-hidden="true" />
      {label ? <span>{label}</span> : null}
    </Button>
  );
}
