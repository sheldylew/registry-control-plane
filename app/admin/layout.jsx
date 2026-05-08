import { redirect } from "next/navigation";

import AdminShell from "@/app/components/admin-shell";
import { requireCurrentUser } from "@/app/lib/server-api";

export default async function AdminLayout({ children }) {
  const user = await requireCurrentUser();
  if (!user) {
    redirect("/login");
  }
  if (!user.is_admin) {
    redirect("/");
  }

  return <AdminShell user={user}>{children}</AdminShell>;
}
