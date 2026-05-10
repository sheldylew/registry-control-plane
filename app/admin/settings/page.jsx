import SettingsPanel from "@/app/components/settings-panel";
import { Panel, PanelHeader } from "@/app/components/ui/panel";
import { apiFetch } from "@/app/lib/server-api";

export default async function SettingsPage() {
  const response = await apiFetch("/api/admin/settings");
  if (!response.ok) {
    throw new Error("Failed to load settings.");
  }
  const payload = await response.json();

  return (
    <div className="space-y-6">
      <Panel className="p-6">
        <PanelHeader
          title="Settings"
          description="Configure deployment values that must be shared between the control plane and registry."
        />
      </Panel>
      <SettingsPanel
        initialPublicOrigin={payload.public_registry_origin}
        initialTimeZone={payload.ui_timezone}
        restartCommand={payload.restart_command}
      />
    </div>
  );
}
