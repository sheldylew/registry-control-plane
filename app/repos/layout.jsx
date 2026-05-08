import { redirect } from "next/navigation";

import AdminShell from "@/app/components/admin-shell";
import { requireCurrentUser } from "@/app/lib/server-api";

export default async function ReposLayout({ children }) {
  const user = await requireCurrentUser();
  if (!user) {
    redirect("/login");
  }

  return <AdminShell user={user} sectionLabel="Registry">{children}</AdminShell>;
}
