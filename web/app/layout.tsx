import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import Link from "next/link";

import { Logo } from "@/components/Logo";
import { THEME_SCRIPT, ThemeToggle } from "@/components/ThemeToggle";

import "./globals.css";

const display = Space_Grotesk({ subsets: ["latin"], weight: ["500"], variable: "--font-display" });
const body = Inter({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-body" });

export const metadata: Metadata = {
  title: "nightly · startup jobs for freshers",
  description: "Wake up to 3 startup jobs worth applying for.",
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
      <body className="min-h-dvh bg-bg font-sans text-text antialiased">
        <div className="mx-auto flex min-h-dvh max-w-md flex-col">
          <header className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-bg/90 px-4 py-3 backdrop-blur">
            <Link href="/"><Logo /></Link>
            <ThemeToggle />
          </header>
          <main className="flex flex-1 flex-col px-4 py-5">{children}</main>
        </div>
      </body>
    </html>
  );
}
