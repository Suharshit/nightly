"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Nav() {
  const path = usePathname();
  const tab = (href: string, label: string) => (
    <Link href={href} aria-current={path === href ? "page" : undefined}
          className={`flex-1 py-2 text-center text-sm ${path === href ? "bg-primary font-medium text-on-primary" : "text-muted hover:bg-card"}`}>
      {label}
    </Link>
  );
  return <nav className="mb-4 grid grid-cols-2 border border-text">{tab("/feed", "Matches")}{tab("/chat", "Chat")}</nav>;
}
