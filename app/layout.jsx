import "./globals.css";

import { ToastProvider } from "@/app/components/ui/toast-provider";

export const metadata = {
  title: "Registry Control Plane",
  description:
    "Production-minded control plane for a self-hosted Docker registry, built for sole developers and homelab operators.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
