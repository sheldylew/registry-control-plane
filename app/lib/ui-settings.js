import { apiFetch } from "@/app/lib/server-api";

const FALLBACK_TIME_ZONE = "America/Los_Angeles";

export async function getUiTimezone() {
  try {
    const response = await apiFetch("/api/ui-settings");
    if (!response.ok) {
      return FALLBACK_TIME_ZONE;
    }
    const payload = await response.json();
    return payload.ui_timezone || FALLBACK_TIME_ZONE;
  } catch {
    return FALLBACK_TIME_ZONE;
  }
}
