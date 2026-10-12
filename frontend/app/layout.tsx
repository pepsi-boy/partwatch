import type { Metadata } from "next";
import Link from "next/link";

import { PUBLIC_API_URL } from "@/lib/api";

import "./globals.css";

export const metadata: Metadata = {
  title: "PartWatch",
  description: "Best Buy price tracker for PC parts: price history, deals, and system status.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="nav" aria-label="Main">
          <div className="nav-inner">
            <Link href="/" className="brand">
              PartWatch
            </Link>
            <Link href="/" className="navlink">
              Parts
            </Link>
            <Link href="/deals" className="navlink">
              Deals
            </Link>
            <Link href="/status" className="navlink">
              Status
            </Link>
            <span className="spacer" />
            <a href={`${PUBLIC_API_URL}/docs`} className="navlink">
              API docs
            </a>
          </div>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
