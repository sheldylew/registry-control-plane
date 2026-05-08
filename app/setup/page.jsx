import { redirect } from "next/navigation";

import SetupForm from "@/app/components/setup-form";
import { apiFetch } from "@/app/lib/server-api";

export default async function SetupPage() {
  const response = await apiFetch("/api/setup/status");
  const payload = response.ok ? await response.json() : { setup_required: true };
  if (!payload.setup_required) {
    redirect("/login");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-xl items-center px-6 py-10">
      <SetupForm initialPublicOrigin={payload.public_registry_origin || ""} />
    </main>
  );
}
