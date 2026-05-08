import { redirect } from "next/navigation";

import LoginForm from "@/app/components/login-form";
import { apiFetch, requireCurrentUser } from "@/app/lib/server-api";

export default async function LoginPage() {
  const setupResponse = await apiFetch("/api/setup/status");
  if (setupResponse.ok) {
    const setup = await setupResponse.json();
    if (setup.setup_required) {
      redirect("/setup");
    }
  }

  const user = await requireCurrentUser();
  if (user?.is_admin) {
    redirect("/admin");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md items-center px-6 py-10">
      <LoginForm />
    </main>
  );
}
