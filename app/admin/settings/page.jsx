import SettingsPanel from "@/app/components/settings-panel";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { readWebBuildInfo } from "@/app/lib/build-info";
import { apiFetch } from "@/app/lib/server-api";

export default async function SettingsPage() {
  const [response, webBuild] = await Promise.all([
    apiFetch("/api/admin/settings"),
    readWebBuildInfo(),
  ]);
  if (!response.ok) {
    throw new Error("Failed to load settings.");
  }
  const payload = await response.json();

  return (
    <div className="space-y-6">
      <Panel className="p-6">
        <PanelHeader
          title="Settings"
          description="Configure registry-facing values and runtime UI defaults for the control plane."
        />
      </Panel>
      <SettingsPanel
        build={{
          api: payload.build,
          web: webBuild,
        }}
        initialPublicOrigin={payload.public_registry_origin}
        initialTimeZone={payload.ui_timezone}
        initialRepositoryTagsPageSize={payload.repository_tags_page_size}
        initialAuditLogRetentionDays={payload.audit_log_retention_days}
        initialAutomaticRegistryStateRebuild={payload.automatic_registry_state_rebuild}
        initialStorageUsageRefreshIntervalSeconds={payload.storage_usage_refresh_interval_seconds}
        restartCommand={payload.restart_command}
      />
    </div>
  );
}
