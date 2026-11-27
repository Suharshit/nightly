"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { DislikeReason, Job } from "@/lib/types";

const APP_URL = (process.env.NEXT_PUBLIC_APP_URL || "").replace(/\/$/, "");

const REASONS: { value: DislikeReason; label: string }[] = [
  { value: "too_senior", label: "Too senior" },
  { value: "wrong_location", label: "Wrong location" },
  { value: "not_interested", label: "Not for me" },
];

function place(j: Job): string {
  if (j.work_mode === "remote" || j.remote) return "Remote";
  return [j.city, j.work_mode === "hybrid" ? "hybrid" : null].filter(Boolean).join(" · ") || "India";
}

function posted(iso: string | null): string | null {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
}

export function shareLink(j: Job): string {
  const text = `${j.title} at ${j.company}\n${j.apply_url ?? ""}\n\n` +
    `Found on nightly, startup jobs for freshers: ${APP_URL}/?ref=wa_share`;
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

export function JobCard({ job }: { job: Job }) {
  const [state, setState] = useState<"idle" | "liked" | "asking" | "disliked">("idle");
  const [error, setError] = useState<string | null>(null);

  async function send(action: "like" | "dislike" | "apply_click" | "share", reason?: DislikeReason) {
    setError(null);
    try {
      await api.feedback(job.id, action, reason);
    } catch (e) {
      // Apply and share must still work if logging fails.
      if (action === "like" || action === "dislike") setError((e as Error).message);
      throw e;
    }
  }

  if (state === "disliked") {
    return (
      <div className="rounded-2xl border border-line px-4 py-3 text-sm text-muted">
        Hidden. You&apos;ll see fewer jobs like {job.company}&apos;s.
      </div>
    );
  }

  const when = posted(job.posted_at);
  return (
    <article className="rounded-2xl bg-card p-4">
      <h3 className="font-display text-base font-medium leading-snug">{job.title}</h3>
      <p className="mt-0.5 text-sm text-muted">
        {job.company} · {place(job)}{when ? ` · ${when}` : ""}
      </p>
      {job.reason && (
        <p className="mt-2 text-sm">
          <span className="mr-1.5 inline-block h-1.5 w-1.5 translate-y-[-2px] rounded-full bg-accent" />
          {job.reason}
        </p>
      )}

      {state === "asking" ? (
        <div className="mt-3">
          <p className="mb-2 text-sm text-muted">Why not this one?</p>
          <div className="flex flex-wrap gap-2">
            {REASONS.map((r) => (
              <button key={r.value} className="rounded-full border border-line px-3 py-1.5 text-sm"
                      onClick={() => send("dislike", r.value).then(() => setState("disliked"), () => {})}>
                {r.label}
              </button>
            ))}
            <button className="px-2 text-sm text-muted" onClick={() => setState("idle")}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-2">
          <button aria-label="Like" aria-pressed={state === "liked"}
                  className={`rounded-full border px-3 py-1.5 text-sm ${state === "liked" ? "border-accent" : "border-line"}`}
                  onClick={() => send("like").then(() => setState("liked"), () => {})}>
            👍
          </button>
          <button aria-label="Not for me" className="rounded-full border border-line px-3 py-1.5 text-sm"
                  onClick={() => setState("asking")}>
            👎
          </button>
          <a href={shareLink(job)} target="_blank" rel="noopener noreferrer"
             onClick={() => { send("share").catch(() => {}); }}
             className="rounded-full border border-line px-3 py-1.5 text-sm">
            Share
          </a>
          {job.apply_url && (
            <a href={job.apply_url} target="_blank" rel="noopener noreferrer"
               onClick={() => { send("apply_click").catch(() => {}); }}
               className="ml-auto rounded-full bg-primary px-4 py-1.5 text-sm font-medium text-on-primary">
              Apply
            </a>
          )}
        </div>
      )}
      {error && <p className="mt-2 text-sm text-muted">Couldn&apos;t save that: {error}</p>}
    </article>
  );
}
