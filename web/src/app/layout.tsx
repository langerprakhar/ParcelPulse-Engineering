import type { Metadata } from "next";
import Link from "next/link";

import { devToolsEnabled } from "@/lib/config";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "ParcelPulse",
    template: "%s · ParcelPulse",
  },
  description: "Track parcels and get notified when they are on their way.",
};

// The navigation depends on runtime configuration, so nothing is prerendered at build time.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="site-header-inner">
            <Link href="/" className="brand">
              <span className="brand-mark" aria-hidden="true" />
              ParcelPulse
            </Link>
            <nav className="site-nav" aria-label="Main">
              <Link href="/">Track</Link>
              <Link href="/shipments">Shipments</Link>
              {devToolsEnabled() ? <Link href="/dev">Developer tools</Link> : null}
            </nav>
          </div>
        </header>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
