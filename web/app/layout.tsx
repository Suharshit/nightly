import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Header } from "@/components/Header";
import { THEME_SCRIPT } from "@/components/ThemeToggle";

import "./globals.css";

// Served from this app (app/fonts, SIL OFL 1.1), so builds never depend on reaching Google Fonts:
// a failed font download broke a Vercel build once.
const display = localFont({
  src: "./fonts/space-grotesk-latin-500.woff2", weight: "500", variable: "--font-display",
  display: "swap",
});
const body = localFont({
  src: "./fonts/inter-latin-var.woff2", weight: "400 500", variable: "--font-body",
  display: "swap",
});

export const metadata: Metadata = {
  title: "nightly · startup jobs for freshers",
  description: "Wake up to a short list of startup jobs you can actually apply for.",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FFFFFF" },
    { media: "(prefers-color-scheme: dark)", color: "#0A0A0B" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="bg-bg font-sans text-text antialiased">
        {/* One frame for every page: a phone-width column, outlined on wider screens. */}
        <div className="mx-auto flex h-dvh max-w-xl flex-col md:border-x md:border-text">
          <Header />
          <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}
