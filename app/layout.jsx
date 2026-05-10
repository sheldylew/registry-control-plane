import "./globals.css";

import ApiBusyOverlay from "@/app/components/ui/api-busy-overlay";
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
        <ToastProvider>
          {children}
          <ApiBusyOverlay />
        </ToastProvider>
      </body>
    </html>
  );
}
