"use client";

import Link from "next/link";

import { Logo } from "@/components/Logo";
import { Menu } from "@/components/Menu";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useSession } from "@/lib/useSession";

/** Logo, theme switch, and (signed in) the "…" menu with your details. */
export function Header() {
  const session = useSession({ required: false });
  return (
    <header className="relative z-20 flex items-center justify-between border-b border-text bg-bg px-4 py-2.5">
      <Link href="/"><Logo /></Link>
      <div className="flex items-center gap-2">
        <ThemeToggle />
        {session && <Menu session={session} />}
      </div>
    </header>
  );
}
