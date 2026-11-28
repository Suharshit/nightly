"use client";

import { useState } from "react";

import { ArrowUpRight, Share, ThumbDown, ThumbUp } from "@/components/Icons";
import { api } from "@/lib/api";
import type { DislikeReason, Job } from "@/lib/types";

const APP_URL = (process.env.NEXT_PUBLIC_APP_URL || "").replace(/\/$/, "");

export const REASONS: { value: DislikeReason; label: string }[] = [
  { value: "too_senior", label: "Too senior" },
  { value: "wrong_location", label: "Wrong location" },
  { value: "not_interested", label: "Not for me" },
];

export type Action = "like" | "dislike" | "apply_click" | "share";

export function place(j: Job): string {
  if (j.work_mode === "remote" || j.remote) return "Remote";
  return [j.city, j.work_mode === "hybrid" ? "hybrid" : null].filter(Boolean).join(" · ") || "India";
}

export function posted(iso: string | null): string | null {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 45) return `${days} days ago`;
  if (days < 365) {
    const months = Math.floor(days / 30.4);
    return months <= 1 ? "over a month ago" : `${months} months ago`;
  }
  return days < 730 ? "over a year ago" : "over 2 years ago";
}

// Jobs older than this get a note that they are still listed. Most active jobs are past it
// (median 63 days, 28 Nov), and every active job was on its company's board in the latest
// nightly run (jobs taken down are expired), so old means long-open, not closed.
const OLD_DAYS = 45;

function stillListed(iso: string | null): boolean {
  return !!iso && Date.now() - new Date(iso).getTime() >= OLD_DAYS * 86_400_000;
}

export function shareLink(j: Job): string {
  const text = `${j.title} at ${j.company}\n${j.apply_url ?? ""}\n\n` +
    `Found on nightly, startup jobs for freshers: ${APP_URL}/?ref=wa_share`;
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

/** Logs an action. Apply and share must still work if logging fails, so callers decide. */
export function sendFeedback(job: Job, action: Action, reason?: DislikeReason) {
  return api.feedback(job.id, action, reason);
}

function years(j: Job): string {
  const lo = j.min_exp_years, hi = j.max_exp_years;
  if (lo === null) return "Not stated";
  if (hi !== null && hi !== lo) return `${lo}–${hi} yrs`;
  return lo === 0 ? "0 yrs (fresher)" : `${lo}+ yrs`;
}

const LEVEL: Record<string, string> = {
  intern: "Internship", fresher: "Fresher", junior: "Junior", mid: "Mid", senior: "Senior",
};

function mode(j: Job): string {
  if (j.work_mode === "remote" || j.remote) return "Remote";
  return j.work_mode ? j.work_mode[0].toUpperCase() + j.work_mode.slice(1) : "Not stated";
}

/** The full job card: every field we hold, with "Not stated" instead of a guess. */
export function JobDetails({ job, badge, fill = false }:
                           { job: Job; badge?: React.ReactNode; fill?: boolean }) {
  const when = posted(job.posted_at);
  const rows: [string, string][] = [
    ["Level", job.seniority ? LEVEL[job.seniority] ?? job.seniority : "Not stated"],
    ["Experience", years(job)],
    ["Work mode", mode(job)],
    ["City", job.city ?? (mode(job) === "Remote" ? "Remote" : "Not stated")],
  ];
  return (
    <article className={`box flex flex-col ${fill ? "flex-1" : ""}`}>
      <div className="flex items-center justify-between gap-2 border-b border-text px-4 py-2 text-xs text-muted">
        <span>
          {when ? `Posted ${when}` : "Post date not stated"}
          {stillListed(job.posted_at) && " · still on their careers page"}
        </span>
        {badge}
      </div>
      <div className="px-4 py-4">
        <h2 className="font-display text-2xl font-medium leading-tight tracking-tight">{job.title}</h2>
        <p className="mt-1 text-sm text-muted">{job.company} · {place(job)}</p>
      </div>
      <dl className="grid grid-cols-2 border-t border-text text-sm">
        {rows.map(([k, v], i) => (
          <div key={k} className={`px-4 py-2.5 ${i % 2 ? "border-l border-text" : ""} ${i > 1 ? "border-t border-text" : ""}`}>
            <dt className="text-xs text-muted">{k}</dt>
            <dd className={v === "Not stated" ? "text-muted" : ""}>{v}</dd>
          </div>
        ))}
      </dl>
      {job.skills.length > 0 && (
        <div className="border-t border-text px-4 py-3">
          <p className="mb-2 text-xs text-muted">Skills</p>
          <div className="flex flex-wrap gap-1.5">
            {job.skills.slice(0, 10).map((s) => <span key={s} className="chip">{s}</span>)}
          </div>
        </div>
      )}
      {job.reason && (
        <div className="border-t border-text px-4 py-3 text-sm">
          <p className="mb-1 text-xs text-muted">Why this match</p>
          <p>
            <span className="mr-1.5 inline-block h-1.5 w-1.5 translate-y-[-2px] bg-accent" />
            {job.reason}
          </p>
        </div>
      )}
      <div className="mt-auto border-t border-text px-4 py-2.5">
        <a href={shareLink(job)} target="_blank" rel="noopener noreferrer"
           onClick={() => { sendFeedback(job, "share").catch(() => {}); }}
           className="inline-flex items-center gap-1.5 text-sm underline underline-offset-4">
          <Share size={16} /> Share on WhatsApp
        </a>
      </div>
    </article>
  );
}

/** A compact card with its own like / not-for-me / Apply, for chat replies. */
export function JobCard({ job }: { job: Job }) {
  const [state, setState] = useState<"idle" | "liked" | "hidden">("idle");
  if (state === "hidden") {
    return <p className="box px-4 py-3 text-sm text-muted">Hidden. You&apos;ll see fewer like this.</p>;
  }
  return (
    <div className="flex flex-col">
      <JobDetails job={job} />
      <div className="grid grid-cols-[1fr_1fr_2fr] border-x border-b border-text">
        <button aria-label="Like" aria-pressed={state === "liked"}
                title="Like"
                className={`flex items-center justify-center py-2.5 ${state === "liked" ? "bg-primary text-on-primary" : "hover:bg-card"}`}
                onClick={() => sendFeedback(job, "like").then(() => setState("liked"), () => {})}>
          <ThumbUp size={18} filled={state === "liked"} />
        </button>
        <button aria-label="Not for me" title="Not for me"
                className="flex items-center justify-center border-l border-text py-2.5 hover:bg-card"
                onClick={() => sendFeedback(job, "dislike", "not_interested")
                  .then(() => setState("hidden"), () => {})}>
          <ThumbDown size={18} />
        </button>
        {job.apply_url ? (
          <a href={job.apply_url} target="_blank" rel="noopener noreferrer"
             onClick={() => { sendFeedback(job, "apply_click").catch(() => {}); }}
             className="flex items-center justify-center gap-1.5 border-l border-text bg-primary py-2.5 text-sm font-medium text-on-primary">
            Apply <ArrowUpRight size={16} />
          </a>
        ) : <span className="border-l border-text" />}
      </div>
    </div>
  );
}
