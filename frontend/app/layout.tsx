import type { Metadata } from "next";
import "./globals.css";
import { LiveProvider } from "@/lib/live";
import Nav from "@/components/Nav";
import Overlays from "@/components/Overlays";

export const metadata: Metadata = {
  title: "Secure IoT Gateway",
  description: "ECC + TLS MQTT gateway: live crypto visualizer, analytics and benchmarks",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LiveProvider>
          <Nav />
          {children}
          <Overlays />
        </LiveProvider>
      </body>
    </html>
  );
}
