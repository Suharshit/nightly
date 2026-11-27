"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Nav() {
  const path = usePathname();
  const tab = (href: string, label: string) => (
    <Link href={href} aria-current={path === href ? "page" : undefined}
          className={`flex-1 rounded-full py-2 text-center text-sm ${path === href ? "bg-card font-medium" : "text-muted"}`}>
      {label}
    </Link>
  );
  return <nav className="mb-4 flex gap-1 rounded-full border border-line p-1">{tab("/feed", "Matches")}{tab("/chat", "Chat")}</nav>;
}
