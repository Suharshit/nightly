"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { JobDetails, REASONS, sendFeedback } from "@/components/JobCard";
import { ApiError, api } from "@/lib/api";
import type { DislikeReason, Job } from "@/lib/types";
import { useSession } from "@/lib/useSession";

type Card = Job & { fresh?: boolean };
type Mark = "liked" | "hidden";

/** Home: one job at a time. Swipe up (phone) or scroll down (PC) for the next, back for the
 *  previous; 👍, 👎 and Apply act on the job on screen. Built from the resume and saved
 *  preferences, with "New since yesterday" jobs first. */
export default function Feed() {
  const router = useRouter();
  const session = useSession();
  const [cards, setCards] = useState<Card[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
  const [index, setIndex] = useState(0);
  const [marks, setMarks] = useState<Record<number, Mark>>({});
  const [asking, setAsking] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setError(null);
    setCards(null);
    setMarks({});
    setIndex(0);
    const timer = setTimeout(() => setSlow(true), 3000);
    try {
      // "New since yesterday" is a bonus: if it fails, the main feed still shows.
      const [feed, latest] = await Promise.all([
        api.feed(), api.newSinceYesterday().catch(() => null),
      ]);
      const fresh = (latest?.jobs ?? []).map((j) => ({ ...j, fresh: true }));
      const seen = new Set(fresh.map((j) => j.id));
      setCards([...fresh, ...feed.jobs.filter((j) => !seen.has(j.id))]);
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) router.replace("/onboard"); // no resume yet
      else setError((e as Error).message);
    } finally {
      clearTimeout(timer);
      setSlow(false);
    }
  }, [router]);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  // Which card fills the screen: the one most in view.
  useEffect(() => {
    const root = scroller.current;
    if (!root || !cards) return;
    const seen = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) setIndex(Number((e.target as HTMLElement).dataset.index));
      }
    }, { root, threshold: 0.6 });
    root.querySelectorAll("[data-index]").forEach((el) => seen.observe(el));
    return () => seen.disconnect();
  }, [cards]);

  const go = useCallback((to: number) => {
    const el = scroller.current?.querySelector(`[data-index="${to}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // The card on screen right now, read from the scroll position (state can lag a smooth scroll).
  const current = useCallback(() => {
    const root = scroller.current;
    return root ? Math.round(root.scrollTop / Math.max(root.clientHeight, 1)) : 0;
  }, []);

  // Keyboard on PC: arrows or j/k move between cards.
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest?.("input, textarea, [aria-expanded=true]")) return;
      if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); go(current() + 1); }
      if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); go(current() - 1); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [go, current]);

  const job = cards?.[index];
  const atEnd = !cards || index >= cards.length;

  async function act(mark: Mark, reason?: DislikeReason) {
    if (!job) return;
    setSaveError(null);
    setAsking(false);
    try {
      await sendFeedback(job, mark === "liked" ? "like" : "dislike", reason);
      setMarks((m) => ({ ...m, [job.id]: mark }));
      const from = current();
      setTimeout(() => go(from + 1), mark === "liked" ? 350 : 600);
    } catch (e) {
      setSaveError((e as Error).message);
    }
  }

  if (error) {
    return (
      <div className="page">
        <div className="box p-4 text-sm">
          <p>{error}</p>
          <button onClick={load} className="btn mt-3">Try again</button>
        </div>
      </div>
    );
  }
  if (cards === null) {
    return (
      <p className="page text-sm text-muted">
        {slow ? "Waking up the server, this can take up to a minute the first time…" : "Finding jobs…"}
      </p>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scroller}
           className="min-h-0 flex-1 snap-y snap-mandatory overflow-y-auto overscroll-contain">
        {cards.map((c, i) => (
          <section key={c.id} data-index={i}
                   className="flex h-full snap-start snap-always flex-col overflow-y-auto px-4 py-4">
            {marks[c.id] === "hidden" ? (
              <div className="box flex flex-1 items-center justify-center p-6 text-center text-sm text-muted">
                Hidden. You&apos;ll see fewer jobs like {c.company}&apos;s.
              </div>
            ) : (
              <JobDetails job={c} fill badge={
                <span className="flex items-center gap-2">
                  {c.fresh && <span className="chip border-accent text-text">New since yesterday</span>}
                  {marks[c.id] === "liked" && <span className="chip bg-primary text-on-primary">Liked</span>}
                  <span className="tabular-nums">{i + 1} / {cards.length}</span>
                </span>
              } />
            )}
            {i === 0 && cards.length > 1 && (
              <p className="mt-3 text-center text-xs text-muted">
                <span className="md:hidden">Swipe up for the next job</span>
                <span className="hidden md:inline">Scroll down (or press ↓) for the next job</span>
              </p>
            )}
          </section>
        ))}
        <section data-index={cards.length}
                 className="flex h-full snap-start snap-always flex-col justify-center px-4 py-4">
          <div className="box flex flex-col gap-3 p-6 text-sm">
            <h2 className="font-display text-xl font-medium">
              {cards.length ? "That's today's list." : "Nothing new right now."}
            </h2>
            <p className="text-muted">
              New jobs arrive every night. Ask the chat to loosen a filter, like
              &ldquo;remote is fine too&rdquo;.
            </p>
            <div className="flex gap-2">
              <button onClick={load} className="btn">Refresh</button>
              <Link href="/chat" className="btn btn-primary">Open chat</Link>
            </div>
          </div>
        </section>
      </div>

      {saveError && <p className="px-4 pb-1 text-xs text-muted">Couldn&apos;t save that: {saveError}</p>}
      {asking && job ? (
        <div className="border-t border-text">
          <p className="px-4 pt-2 text-xs text-muted">Why not this one?</p>
          <div className="grid grid-cols-2 gap-px bg-text p-px sm:grid-cols-4">
            {REASONS.map((r) => (
              <button key={r.value} onClick={() => act("hidden", r.value)}
                      className="bg-bg px-2 py-3 text-sm hover:bg-card">{r.label}</button>
            ))}
            <button onClick={() => setAsking(false)} className="bg-bg px-2 py-3 text-sm text-muted">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-[1fr_1fr_2fr] border-t border-text">
          <button aria-label="Like" disabled={atEnd || !!(job && marks[job.id])}
                  aria-pressed={!!job && marks[job.id] === "liked"}
                  onClick={() => act("liked")}
                  className="py-4 text-lg hover:bg-card disabled:opacity-40">👍</button>
          <button aria-label="Not for me" disabled={atEnd || !!(job && marks[job.id])}
                  onClick={() => setAsking(true)}
                  className="border-l border-text py-4 text-lg hover:bg-card disabled:opacity-40">👎</button>
          {job?.apply_url && !atEnd ? (
            <a href={job.apply_url} target="_blank" rel="noopener noreferrer"
               onClick={() => { sendFeedback(job, "apply_click").catch(() => {}); }}
               className="flex items-center justify-center border-l border-text bg-primary font-medium text-on-primary">
              Apply
            </a>
          ) : (
            <span className="flex items-center justify-center border-l border-text text-sm text-muted">
              Apply
            </span>
          )}
        </div>
      )}
    </div>
  );
}
