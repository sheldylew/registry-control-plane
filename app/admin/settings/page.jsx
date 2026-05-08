import SettingsPanel from "@/app/components/settings-panel";
import { apiFetch } from "@/app/lib/server-api";

export default async function SettingsPage() {
  const response = await apiFetch("/api/admin/settings");
  if (!response.ok) {
    throw new Error("Failed to load settings.");
  }
  const payload = await response.json();

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-white">Settings</h2>
        <p className="mt-2 text-sm leading-6 text-slate-300">
          Configure deployment values that must be shared between the control plane and registry.
        </p>
      </div>
      <SettingsPanel
        initialPublicOrigin={payload.public_registry_origin}
        restartCommand={payload.restart_command}
      />
    </div>
  );
}
