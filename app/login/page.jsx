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
    <main className="relative mx-auto flex min-h-screen max-w-7xl items-center overflow-hidden px-4 py-6 sm:px-6 sm:py-10 lg:px-8">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.16),_transparent_28%),radial-gradient(circle_at_80%_18%,_rgba(52,211,153,0.12),_transparent_20%),linear-gradient(180deg,_rgba(2,6,23,0.08),_rgba(2,6,23,0.42))]" />
        <svg
          className="absolute -left-20 top-8 h-[24rem] w-[24rem] opacity-60 sm:h-[28rem] sm:w-[28rem] lg:left-0"
          viewBox="0 0 420 420"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <rect x="28" y="34" width="132" height="132" rx="24" stroke="#94A3B8" strokeOpacity="0.18" strokeWidth="2" />
          <rect x="112" y="86" width="176" height="176" rx="28" stroke="#22D3EE" strokeOpacity="0.2" strokeWidth="2" />
          <rect x="198" y="28" width="154" height="154" rx="26" stroke="#CBD5E1" strokeOpacity="0.14" strokeWidth="2" />
          <rect x="216" y="182" width="144" height="144" rx="24" stroke="#34D399" strokeOpacity="0.18" strokeWidth="2" />
          <path d="M42 238H184" stroke="#94A3B8" strokeOpacity="0.18" strokeWidth="2" />
          <path d="M98 286H286" stroke="#CBD5E1" strokeOpacity="0.16" strokeWidth="2" />
          <path d="M126 334H354" stroke="#34D399" strokeOpacity="0.14" strokeWidth="2" />
          <circle cx="86" cy="198" r="7" fill="#22D3EE" fillOpacity="0.24" />
          <circle cx="304" cy="116" r="8" fill="#E2E8F0" fillOpacity="0.18" />
          <circle cx="248" cy="306" r="10" fill="#34D399" fillOpacity="0.18" />
        </svg>
        <div className="absolute -bottom-24 right-[-8rem] h-[28rem] w-[32rem] rounded-full bg-[radial-gradient(circle,_rgba(34,211,238,0.12),_transparent_62%)] blur-3xl" />
        <div className="absolute inset-y-0 right-0 w-full bg-[linear-gradient(90deg,_rgba(2,6,23,0.12),_rgba(2,6,23,0.62)_52%,_rgba(2,6,23,0.9)_100%)] lg:w-3/5" />
      </div>

      <div className="relative z-10 mx-auto w-full max-w-md">
          <LoginForm />
      </div>
    </main>
  );
}
