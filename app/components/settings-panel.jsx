"use client";

import { useState } from "react";
import { Combobox, ComboboxButton, ComboboxInput, ComboboxOption, ComboboxOptions, Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import { CheckIcon, ChevronUpDownIcon } from "@heroicons/react/20/solid";

import Alert from "@/app/components/ui/alert";
import Button from "@/app/components/ui/button";
import DetailList from "@/app/components/ui/detail-list";
import FormDialog from "@/app/components/ui/form-dialog";
import { Field, Input } from "@/app/components/ui/form";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import Switch from "@/app/components/ui/switch";
import { isValidPublicOrigin, normalizeTextInput, readApiErrorDetail } from "@/app/lib/user-form";

const FALLBACK_TIME_ZONES = [
  "UTC",
  "Africa/Cairo",
  "Africa/Johannesburg",
  "America/Anchorage",
  "America/Argentina/Buenos_Aires",
  "America/Bogota",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Mexico_City",
  "America/New_York",
  "America/Phoenix",
  "America/Sao_Paulo",
  "America/Toronto",
  "Asia/Dubai",
  "Asia/Hong_Kong",
  "Asia/Kolkata",
  "Asia/Seoul",
  "Asia/Shanghai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Europe/Amsterdam",
  "Europe/Berlin",
  "Europe/London",
  "Europe/Madrid",
  "Europe/Paris",
  "Pacific/Auckland",
  "Pacific/Honolulu",
];

const STORAGE_USAGE_INTERVAL_OPTIONS = [
  { value: "0", label: "Disabled", detail: "Only refresh when maintenance actions touch storage state." },
  { value: "300", label: "Every 5 minutes", detail: "Fastest background refresh for active troubleshooting." },
  { value: "900", label: "Every 15 minutes", detail: "Reasonable default for a busy registry." },
  { value: "1800", label: "Every 30 minutes", detail: "Lower background churn while staying fairly current." },
  { value: "3600", label: "Every 1 hour", detail: "Good default when storage does not change constantly." },
  { value: "21600", label: "Every 6 hours", detail: "Useful when usage trends matter more than immediate freshness." },
  { value: "43200", label: "Every 12 hours", detail: "Twice-daily background refresh." },
  { value: "86400", label: "Every 24 hours", detail: "Lightest scheduled refresh." },
  { value: "custom", label: "Custom", detail: "Enter an exact number of seconds." },
];

const DEFAULT_PAGE_SIZE_OPTIONS = [
  { value: "5", label: "5 items", detail: "Smallest preset for very compact list views." },
  { value: "10", label: "10 items", detail: "Keeps list views compact and easy to scan." },
  { value: "25", label: "25 items", detail: "A balanced default for denser admin workflows." },
  { value: "50", label: "50 items", detail: "Shows more rows before paging through long lists." },
  { value: "100", label: "100 items", detail: "Maximum page size for operators who want fewer page changes." },
  { value: "custom", label: "Custom", detail: "Enter any whole number from 1 to 100." },
];

const AUDIT_LOG_RETENTION_OPTIONS = [
  { value: "5", label: "5 days", detail: "Most aggressive cleanup when audit history is only needed briefly." },
  { value: "15", label: "15 days", detail: "A shorter retention window that still keeps a couple of weeks of history." },
  { value: "30", label: "30 days", detail: "Keeps a month of audit and completed maintenance history." },
  { value: "60", label: "60 days", detail: "Retains a longer operational trail before pruning old rows." },
  { value: "custom", label: "Custom", detail: "Enter any whole number of days." },
];

function formatStorageUsageInterval(seconds) {
  if (!seconds) {
    return "Disabled";
  }
  const minutes = seconds / 60;
  const hours = seconds / 3600;
  if (Number.isInteger(hours) && hours >= 1) {
    return `Every ${hours} hour${hours === 1 ? "" : "s"}`;
  }
  if (Number.isInteger(minutes) && minutes >= 1) {
    return `Every ${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  return `Every ${seconds} seconds`;
}

function storageUsageIntervalPresetForValue(value) {
  const normalized = String(Number(value) || 0);
  return STORAGE_USAGE_INTERVAL_OPTIONS.some((option) => option.value === normalized) ? normalized : "custom";
}

function pageSizePresetForValue(value) {
  const normalized = String(Number(value) || 0);
  return DEFAULT_PAGE_SIZE_OPTIONS.some((option) => option.value === normalized) ? normalized : "custom";
}

function formatAuditLogRetentionDays(days) {
  const normalized = Number(days) || 0;
  return `${normalized} day${normalized === 1 ? "" : "s"}`;
}

function auditLogRetentionPresetForValue(value) {
  const normalized = String(Number(value) || 0);
  return AUDIT_LOG_RETENTION_OPTIONS.some((option) => option.value === normalized) ? normalized : "custom";
}

function formatBuildTimestamp(value) {
  if (!value) {
    return "Unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toISOString();
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

function standardTimeZones(selectedTimeZone) {
  const supportedTimeZones =
    typeof Intl !== "undefined" && typeof Intl.supportedValuesOf === "function"
      ? Intl.supportedValuesOf("timeZone")
      : [];
  return Array.from(new Set([...supportedTimeZones, ...FALLBACK_TIME_ZONES, selectedTimeZone].filter(Boolean))).sort();
}

function formatTimeZoneLabel(timeZone) {
  return timeZone.replaceAll("_", " ");
}

function readCookie(name) {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split("=")[1];
}

function TimeZonePicker({ value, onChange }) {
  const [query, setQuery] = useState("");
  const timeZones = standardTimeZones(value);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleTimeZones = normalizedQuery
    ? timeZones.filter((timeZone) => {
        const searchable = `${timeZone} ${formatTimeZoneLabel(timeZone)}`.toLowerCase();
        return searchable.includes(normalizedQuery);
      })
    : timeZones;

  function selectTimeZone(nextTimeZone) {
    if (!nextTimeZone) {
      return;
    }
    onChange(nextTimeZone);
    setQuery("");
  }

  return (
    <Combobox value={value} onChange={selectTimeZone} onClose={() => setQuery("")}>
      <div className="relative">
        <ComboboxInput
          aria-label="UI timezone"
          className="w-full rounded-md border border-white/10 bg-slate-950 px-3 py-2 pr-10 text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-300/50 focus:ring-2 focus:ring-cyan-300/10 disabled:cursor-not-allowed disabled:opacity-60"
          displayValue={(timeZone) => timeZone || ""}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search timezones"
          autoComplete="off"
        />
        <ComboboxButton
          aria-label="Open timezone picker"
          className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 transition hover:text-cyan-200"
        >
          <ChevronUpDownIcon aria-hidden="true" className="size-5" />
        </ComboboxButton>
        <ComboboxOptions
          transition
          className="absolute z-20 mt-2 max-h-72 w-full overflow-auto rounded-lg border border-white/10 bg-slate-950 py-1 text-sm shadow-2xl shadow-slate-950/50 outline-none data-[closed]:data-[leave]:opacity-0 data-[leave]:transition data-[leave]:duration-100 data-[leave]:ease-in"
        >
          {visibleTimeZones.length ? (
            visibleTimeZones.map((timeZone) => (
              <ComboboxOption
                key={timeZone}
                value={timeZone}
                className="group relative cursor-default select-none py-2.5 pl-9 pr-4 text-white data-[focus]:bg-cyan-400 data-[focus]:text-slate-950 data-[focus]:outline-none"
              >
                <span className="block truncate font-medium">{formatTimeZoneLabel(timeZone)}</span>
                <span className="block truncate text-xs text-slate-400 group-data-[focus]:text-slate-800">{timeZone}</span>
                <span className="absolute inset-y-0 left-0 hidden items-center pl-2 text-cyan-300 group-data-[focus]:text-slate-950 group-data-[selected]:flex">
                  <CheckIcon aria-hidden="true" className="size-5" />
                </span>
              </ComboboxOption>
            ))
          ) : (
            <div className="px-3 py-2.5 text-sm text-slate-400">No timezones match that search.</div>
          )}
        </ComboboxOptions>
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Standard IANA timezone used for timestamps throughout the admin UI.
      </p>
    </Combobox>
  );
}

function StorageUsageIntervalPicker({ value, onPresetChange }) {
  const selectedOption =
    STORAGE_USAGE_INTERVAL_OPTIONS.find((option) => option.value === value) ||
    STORAGE_USAGE_INTERVAL_OPTIONS[STORAGE_USAGE_INTERVAL_OPTIONS.length - 1];

  return (
    <Listbox value={selectedOption} by="value" onChange={onPresetChange}>
      <div className="relative">
        <ListboxButton className="grid w-full cursor-default grid-cols-1 rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-left text-white outline-none transition hover:border-cyan-400/40 focus-visible:border-cyan-400 focus-visible:ring-2 focus-visible:ring-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-60">
          <span className="block truncate font-medium">{selectedOption.label}</span>
          <span className="block truncate pr-6 text-xs text-slate-400">{selectedOption.detail}</span>
          <ChevronUpDownIcon aria-hidden="true" className="pointer-events-none absolute right-3 top-3.5 size-5 text-slate-400" />
        </ListboxButton>
        <ListboxOptions
          transition
          className="absolute z-[60] mt-2 max-h-72 w-full overflow-auto rounded-lg border border-white/10 bg-slate-950 py-1 text-sm shadow-2xl shadow-slate-950/50 outline-none data-[closed]:data-[leave]:opacity-0 data-[leave]:transition data-[leave]:duration-100 data-[leave]:ease-in"
        >
          {STORAGE_USAGE_INTERVAL_OPTIONS.map((option) => (
            <ListboxOption
              key={option.value}
              value={option}
              className="group relative cursor-default select-none py-2.5 pl-9 pr-4 text-white data-[focus]:bg-cyan-400 data-[focus]:text-slate-950 data-[focus]:outline-none"
            >
              <span className="block truncate font-medium">{option.label}</span>
              <span className="block truncate text-xs text-slate-400 group-data-[focus]:text-slate-800">{option.detail}</span>
              <span className="absolute inset-y-0 left-0 hidden items-center pl-2 text-cyan-300 group-data-[focus]:text-slate-950 group-data-[selected]:flex">
                <CheckIcon aria-hidden="true" className="size-5" />
              </span>
            </ListboxOption>
          ))}
        </ListboxOptions>
      </div>
    </Listbox>
  );
}

function DefaultPageSizePicker({ value, onPresetChange }) {
  const selectedOption =
    DEFAULT_PAGE_SIZE_OPTIONS.find((option) => option.value === value) ||
    DEFAULT_PAGE_SIZE_OPTIONS[DEFAULT_PAGE_SIZE_OPTIONS.length - 1];

  return (
    <Listbox value={selectedOption} by="value" onChange={onPresetChange}>
      <div className="relative">
        <ListboxButton className="grid w-full cursor-default grid-cols-1 rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-left text-white outline-none transition hover:border-cyan-400/40 focus-visible:border-cyan-400 focus-visible:ring-2 focus-visible:ring-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-60">
          <span className="block truncate font-medium">{selectedOption.label}</span>
          <span className="block truncate pr-6 text-xs text-slate-400">{selectedOption.detail}</span>
          <ChevronUpDownIcon aria-hidden="true" className="pointer-events-none absolute right-3 top-3.5 size-5 text-slate-400" />
        </ListboxButton>
        <ListboxOptions
          transition
          className="absolute z-[60] mt-2 max-h-72 w-full overflow-auto rounded-lg border border-white/10 bg-slate-950 py-1 text-sm shadow-2xl shadow-slate-950/50 outline-none data-[closed]:data-[leave]:opacity-0 data-[leave]:transition data-[leave]:duration-100 data-[leave]:ease-in"
        >
          {DEFAULT_PAGE_SIZE_OPTIONS.map((option) => (
            <ListboxOption
              key={option.value}
              value={option}
              className="group relative cursor-default select-none py-2.5 pl-9 pr-4 text-white data-[focus]:bg-cyan-400 data-[focus]:text-slate-950 data-[focus]:outline-none"
            >
              <span className="block truncate font-medium">{option.label}</span>
              <span className="block truncate text-xs text-slate-400 group-data-[focus]:text-slate-800">{option.detail}</span>
              <span className="absolute inset-y-0 left-0 hidden items-center pl-2 text-cyan-300 group-data-[focus]:text-slate-950 group-data-[selected]:flex">
                <CheckIcon aria-hidden="true" className="size-5" />
              </span>
            </ListboxOption>
          ))}
        </ListboxOptions>
      </div>
    </Listbox>
  );
}

function AuditLogRetentionPicker({ value, onPresetChange }) {
  const selectedOption =
    AUDIT_LOG_RETENTION_OPTIONS.find((option) => option.value === value) ||
    AUDIT_LOG_RETENTION_OPTIONS[AUDIT_LOG_RETENTION_OPTIONS.length - 1];

  return (
    <Listbox value={selectedOption} by="value" onChange={onPresetChange}>
      <div className="relative">
        <ListboxButton className="grid w-full cursor-default grid-cols-1 rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-left text-white outline-none transition hover:border-cyan-400/40 focus-visible:border-cyan-400 focus-visible:ring-2 focus-visible:ring-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-60">
          <span className="block truncate font-medium">{selectedOption.label}</span>
          <span className="block truncate pr-6 text-xs text-slate-400">{selectedOption.detail}</span>
          <ChevronUpDownIcon aria-hidden="true" className="pointer-events-none absolute right-3 top-3.5 size-5 text-slate-400" />
        </ListboxButton>
        <ListboxOptions
          transition
          className="absolute z-[60] mt-2 max-h-72 w-full overflow-auto rounded-lg border border-white/10 bg-slate-950 py-1 text-sm shadow-2xl shadow-slate-950/50 outline-none data-[closed]:data-[leave]:opacity-0 data-[leave]:transition data-[leave]:duration-100 data-[leave]:ease-in"
        >
          {AUDIT_LOG_RETENTION_OPTIONS.map((option) => (
            <ListboxOption
              key={option.value}
              value={option}
              className="group relative cursor-default select-none py-2.5 pl-9 pr-4 text-white data-[focus]:bg-cyan-400 data-[focus]:text-slate-950 data-[focus]:outline-none"
            >
              <span className="block truncate font-medium">{option.label}</span>
              <span className="block truncate text-xs text-slate-400 group-data-[focus]:text-slate-800">{option.detail}</span>
              <span className="absolute inset-y-0 left-0 hidden items-center pl-2 text-cyan-300 group-data-[focus]:text-slate-950 group-data-[selected]:flex">
                <CheckIcon aria-hidden="true" className="size-5" />
              </span>
            </ListboxOption>
          ))}
        </ListboxOptions>
      </div>
    </Listbox>
  );
}

export default function SettingsPanel({
  build,
  initialPublicOrigin,
  initialTimeZone,
  initialRepositoryTagsPageSize = 10,
  initialAuditLogRetentionDays = 30,
  initialAutomaticRegistryStateRebuild = false,
  initialStorageUsageRefreshIntervalSeconds = 3600,
  restartCommand,
}) {
  const [publicOrigin, setPublicOrigin] = useState(initialPublicOrigin || "");
  const [draftPublicOrigin, setDraftPublicOrigin] = useState(initialPublicOrigin || "");
  const [timeZone, setTimeZone] = useState(initialTimeZone || "America/Los_Angeles");
  const [draftTimeZone, setDraftTimeZone] = useState(initialTimeZone || "America/Los_Angeles");
  const [repositoryTagsPageSize, setRepositoryTagsPageSize] = useState(Number(initialRepositoryTagsPageSize) || 10);
  const [draftRepositoryTagsPageSize, setDraftRepositoryTagsPageSize] = useState(String(Number(initialRepositoryTagsPageSize) || 10));
  const [draftRepositoryTagsPageSizePreset, setDraftRepositoryTagsPageSizePreset] = useState(
    pageSizePresetForValue(initialRepositoryTagsPageSize),
  );
  const [auditLogRetentionDays, setAuditLogRetentionDays] = useState(Number(initialAuditLogRetentionDays) || 30);
  const [draftAuditLogRetentionDays, setDraftAuditLogRetentionDays] = useState(
    String(Number(initialAuditLogRetentionDays) || 30),
  );
  const [draftAuditLogRetentionPreset, setDraftAuditLogRetentionPreset] = useState(
    auditLogRetentionPresetForValue(initialAuditLogRetentionDays),
  );
  const [automaticRebuild, setAutomaticRebuild] = useState(Boolean(initialAutomaticRegistryStateRebuild));
  const [draftAutomaticRebuild, setDraftAutomaticRebuild] = useState(Boolean(initialAutomaticRegistryStateRebuild));
  const [storageUsageRefreshIntervalSeconds, setStorageUsageRefreshIntervalSeconds] = useState(
    Number(initialStorageUsageRefreshIntervalSeconds) || 0,
  );
  const [draftStorageUsageRefreshIntervalSeconds, setDraftStorageUsageRefreshIntervalSeconds] = useState(
    String(Number(initialStorageUsageRefreshIntervalSeconds) || 0),
  );
  const [draftStorageUsageRefreshPreset, setDraftStorageUsageRefreshPreset] = useState(
    storageUsageIntervalPresetForValue(initialStorageUsageRefreshIntervalSeconds),
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [open, setOpen] = useState(false);
  const normalizedOrigin = normalizeTextInput(draftPublicOrigin).replace(/\/$/, "");
  const normalizedTimeZone = normalizeTextInput(draftTimeZone);
  const parsedStorageUsageRefreshIntervalSeconds = Number(draftStorageUsageRefreshIntervalSeconds);
  const parsedRepositoryTagsPageSize = Number(draftRepositoryTagsPageSize);
  const parsedAuditLogRetentionDays = Number(draftAuditLogRetentionDays);
  const hasValidRepositoryTagsPageSize =
    Number.isInteger(parsedRepositoryTagsPageSize) &&
    parsedRepositoryTagsPageSize >= 1 &&
    parsedRepositoryTagsPageSize <= 100;
  const hasValidAuditLogRetentionDays =
    Number.isInteger(parsedAuditLogRetentionDays) &&
    parsedAuditLogRetentionDays >= 1;
  const hasValidStorageUsageInterval =
    Number.isInteger(parsedStorageUsageRefreshIntervalSeconds) &&
    parsedStorageUsageRefreshIntervalSeconds >= 0 &&
    parsedStorageUsageRefreshIntervalSeconds <= 86400;
  const canSubmit =
    isValidPublicOrigin(normalizedOrigin) &&
    Boolean(normalizedTimeZone) &&
    hasValidRepositoryTagsPageSize &&
    hasValidAuditLogRetentionDays &&
    hasValidStorageUsageInterval;

  function openDialog() {
    setDraftPublicOrigin(publicOrigin);
    setDraftTimeZone(timeZone);
    setDraftRepositoryTagsPageSize(String(repositoryTagsPageSize));
    setDraftRepositoryTagsPageSizePreset(pageSizePresetForValue(repositoryTagsPageSize));
    setDraftAuditLogRetentionDays(String(auditLogRetentionDays));
    setDraftAuditLogRetentionPreset(auditLogRetentionPresetForValue(auditLogRetentionDays));
    setDraftAutomaticRebuild(automaticRebuild);
    setDraftStorageUsageRefreshIntervalSeconds(String(storageUsageRefreshIntervalSeconds));
    setDraftStorageUsageRefreshPreset(storageUsageIntervalPresetForValue(storageUsageRefreshIntervalSeconds));
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

  async function onSubmit(event) {
    event.preventDefault();
    if (!canSubmit) {
      setError("Enter a valid public origin, audit retention, and default page size.");
      return;
    }

    setPending(true);
    setError("");
    setMessage("");
    const response = await fetch("/api/admin/settings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": readCookie("rcr_csrf"),
      },
      body: JSON.stringify({
        public_registry_origin: normalizedOrigin,
        ui_timezone: normalizedTimeZone,
        repository_tags_page_size: parsedRepositoryTagsPageSize,
        audit_log_retention_days: parsedAuditLogRetentionDays,
        automatic_registry_state_rebuild: draftAutomaticRebuild,
        storage_usage_refresh_interval_seconds: parsedStorageUsageRefreshIntervalSeconds,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    setPending(false);

    if (!response.ok) {
      setError(readApiErrorDetail(payload, "Could not update settings."));
      return;
    }

    setPublicOrigin(payload.settings.public_registry_origin);
    setDraftPublicOrigin(payload.settings.public_registry_origin);
    setTimeZone(payload.settings.ui_timezone);
    setDraftTimeZone(payload.settings.ui_timezone);
    setRepositoryTagsPageSize(payload.settings.repository_tags_page_size);
    setDraftRepositoryTagsPageSize(String(payload.settings.repository_tags_page_size));
    setDraftRepositoryTagsPageSizePreset(pageSizePresetForValue(payload.settings.repository_tags_page_size));
    setAuditLogRetentionDays(payload.settings.audit_log_retention_days);
    setDraftAuditLogRetentionDays(String(payload.settings.audit_log_retention_days));
    setDraftAuditLogRetentionPreset(auditLogRetentionPresetForValue(payload.settings.audit_log_retention_days));
    setAutomaticRebuild(payload.settings.automatic_registry_state_rebuild);
    setDraftAutomaticRebuild(payload.settings.automatic_registry_state_rebuild);
    setStorageUsageRefreshIntervalSeconds(payload.settings.storage_usage_refresh_interval_seconds);
    setDraftStorageUsageRefreshIntervalSeconds(String(payload.settings.storage_usage_refresh_interval_seconds));
    setDraftStorageUsageRefreshPreset(
      storageUsageIntervalPresetForValue(payload.settings.storage_usage_refresh_interval_seconds),
    );
    setMessage(payload.restart_command || "");
    setOpen(false);
  }

  return (
    <>
      <Panel className="p-4 sm:p-6">
        <PanelHeader
          title="Runtime settings"
          description="Review the registry-facing origin plus the runtime defaults that shape the control-plane UI and retention behavior."
          action={(
            <Button type="button" onClick={openDialog} size="lg" className="w-full sm:w-auto">
              Edit
            </Button>
          )}
        />

        <div className="mt-6">
          <DetailList
            items={[
              {
                label: "Public origin",
                value: <code className="break-all text-sm text-white">{publicOrigin || "Not configured"}</code>,
              },
              {
                label: "Registry restart",
                value: <code className="break-all text-sm text-white">{restartCommand}</code>,
              },
              {
                label: "UI timezone",
                value: <code className="break-all text-sm text-white">{timeZone}</code>,
              },
              {
                label: "Default items per page",
                value: <code className="text-sm text-white">{repositoryTagsPageSize}</code>,
              },
              {
                label: "Audit pruning retention",
                value: <code className="text-sm text-white">{formatAuditLogRetentionDays(auditLogRetentionDays)}</code>,
              },
              {
                label: "Automatic rebuild",
                value: automaticRebuild ? "Enabled on API startup" : "Disabled",
              },
              {
                label: "Storage usage refresh",
                value: formatStorageUsageInterval(storageUsageRefreshIntervalSeconds),
              },
              {
                label: "Change behavior",
                value: "Origin changes require a registry restart. Timezone, page size, audit retention, and refresh interval changes apply without restarting services.",
              },
            ]}
          />
        </div>

        {message ? (
          <Alert tone="amber" className="mt-6">
            <p>Registry restart required after the latest settings change.</p>
            <code className="mt-2 block break-all rounded-lg bg-slate-950 px-3 py-2 text-amber-50">{message}</code>
          </Alert>
        ) : null}
      </Panel>

      <Panel className="p-4 sm:p-6">
        <PanelHeader
          title="Build information"
          description="Read-only metadata baked into the running API and web images."
        />

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
      </Panel>

      <FormDialog
        open={open}
        onClose={closeDialog}
        eyebrow="Settings"
        title="Edit settings"
        description="Update the external registry origin, UI timezone, audit retention, default page size, startup rebuild behavior, and storage usage refresh interval."
        onSubmit={onSubmit}
        submitLabel="Save settings"
        submitPendingLabel="Saving..."
        pending={pending}
        disabled={!canSubmit}
        error={error}
      >
        <Field label="Public registry origin">
          <Input
            autoFocus
            value={draftPublicOrigin}
            onChange={(event) => setDraftPublicOrigin(event.target.value)}
            required
            maxLength={255}
          />
        </Field>
        <div className="block">
          <span className="text-sm font-medium text-slate-200">UI timezone</span>
          <span className="mt-2 block">
            <TimeZonePicker
              value={draftTimeZone}
              onChange={setDraftTimeZone}
            />
          </span>
        </div>
        <Field label="Default items per page">
          <DefaultPageSizePicker
            value={draftRepositoryTagsPageSizePreset}
            onPresetChange={(option) => {
              setDraftRepositoryTagsPageSizePreset(option.value);
              if (option.value !== "custom") {
                setDraftRepositoryTagsPageSize(option.value);
              }
            }}
          />
          {draftRepositoryTagsPageSizePreset === "custom" ? (
            <Input
              className="mt-3"
              value={draftRepositoryTagsPageSize}
              onChange={(event) => setDraftRepositoryTagsPageSize(event.target.value)}
              required
              min={1}
              max={100}
              step={1}
              type="number"
            />
          ) : null}
          <span className="mt-2 block text-xs text-slate-400">
            Presets cover the common sizes. Use Custom to enter any whole number from 1 to 100.
          </span>
        </Field>
        <Field label="Audit pruning retention">
          <AuditLogRetentionPicker
            value={draftAuditLogRetentionPreset}
            onPresetChange={(option) => {
              setDraftAuditLogRetentionPreset(option.value);
              if (option.value !== "custom") {
                setDraftAuditLogRetentionDays(option.value);
              }
            }}
          />
          {draftAuditLogRetentionPreset === "custom" ? (
            <Input
              className="mt-3"
              value={draftAuditLogRetentionDays}
              onChange={(event) => setDraftAuditLogRetentionDays(event.target.value)}
              required
              min={1}
              step={1}
              type="number"
            />
          ) : null}
          <span className="mt-2 block text-xs text-slate-400">
            Presets cover the common retention windows. Use Custom to enter any whole number of days.
          </span>
        </Field>
        <div className="rounded-lg border border-white/10 bg-slate-950/60 p-4">
          <Switch
            checked={draftAutomaticRebuild}
            onChange={setDraftAutomaticRebuild}
            label="Automatic registry state rebuild"
            description="Queue a full registry state rebuild when the API starts, unless a rebuild or maintenance job is already active."
            align="start"
          />
        </div>
        <Field label="Storage usage refresh interval">
          <StorageUsageIntervalPicker
            value={draftStorageUsageRefreshPreset}
            onPresetChange={(option) => {
              setDraftStorageUsageRefreshPreset(option.value);
              if (option.value !== "custom") {
                setDraftStorageUsageRefreshIntervalSeconds(option.value);
              }
            }}
          />
          {draftStorageUsageRefreshPreset === "custom" ? (
            <Input
              className="mt-3"
              value={draftStorageUsageRefreshIntervalSeconds}
              onChange={(event) => setDraftStorageUsageRefreshIntervalSeconds(event.target.value)}
              required
              min={0}
              max={86400}
              step={1}
              type="number"
            />
          ) : null}
          <span className="mt-2 block text-xs text-slate-400">
            Presets cover the common intervals. Use Custom to enter an exact number of seconds from 0 to 86400.
          </span>
        </Field>
      </FormDialog>
    </>
  );
}
