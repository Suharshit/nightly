"use client";

import type { Session } from "@supabase/supabase-js";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { DeleteData } from "@/components/DeleteData";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import type { Me } from "@/lib/types";

const LEVEL: Record<string, string> = { student: "Student", fresher: "Fresher", junior: "1–2 yrs" };

/** The "…" menu: who you are (name, level, remote), where to go, and Delete my data. */
export function Menu({ session }: { session: Session }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && !me) api.me().then(setMe, () => {});
  }, [open, me]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape"
          : !panel.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const meta = session.user.user_metadata ?? {};
  const name: string = meta.full_name || meta.name || session.user.email || "You";
  const level = me?.prefs.level;

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/");
  }

  const item = "block w-full border-t border-text px-4 py-2.5 text-left text-sm hover:bg-bg";
  return (
    <div ref={panel} className="relative">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Menu"
              className="border border-text px-2.5 py-1.5 text-sm leading-none text-text hover:bg-card">
        •••
      </button>
      {open && (
        <div className="box absolute right-0 top-full mt-2 w-72">
          <div className="px-4 py-3">
            <p className="truncate font-display text-base font-medium">{name}</p>
            {session.user.email && name !== session.user.email && (
              <p className="truncate text-xs text-muted">{session.user.email}</p>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="chip">{level ? LEVEL[level] ?? level : me ? "Level not set" : "…"}</span>
              {me && (
                <span className={`chip ${me.prefs.remote ? "bg-primary text-on-primary" : ""}`}>
                  Remote: {me.prefs.remote ? "T" : "F"}
                </span>
              )}
              {me?.prefs.cities?.slice(0, 3).map((c) => <span key={c} className="chip">{c}</span>)}
            </div>
          </div>
          <Link href="/feed" className={item} onClick={() => setOpen(false)}>Matches</Link>
          <Link href="/chat" className={item} onClick={() => setOpen(false)}>Chat</Link>
          <Link href="/onboard" className={item} onClick={() => setOpen(false)}>Edit preferences</Link>
          <Link href="/bug" className={item} onClick={() => setOpen(false)}>Report a bug</Link>
          <Link href="/privacy" className={item} onClick={() => setOpen(false)}>Privacy</Link>
          <button className={item} onClick={signOut}>Sign out</button>
          <div className="border-t border-text px-4 py-3"><DeleteData /></div>
        </div>
      )}
    </div>
  );
}
