"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { Stats } from "@/lib/types";
import { useSession } from "@/lib/useSession";

const pct = (x: number | null) => (x === null ? "–" : `${(x * 100).toFixed(1)}%`);
const ms = (x: number | null) => (x === null ? "–" : `${Math.round(x)} ms`);
const num = (x: number | null) => (x === null ? "–" : String(Math.round(x * 100) / 100));

function Table({ title, rows }: { title: string; rows: [string, string | number][] }) {
  return (
    <section className="rounded-2xl bg-card p-4">
      <h2 className="mb-2 font-display text-base font-medium">{title}</h2>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className="text-right tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Admin-only usage numbers, straight from the database. The README quotes these. */
export default function StatsPage() {
  const session = useSession();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    api.stats().then(setStats, (e) =>
      setError(e instanceof ApiError && e.status === 403 ? "This page is for admins only." : (e as Error).message));
  }, [session]);

  if (session === undefined) return null;
  if (error) return <p className="text-sm text-muted">{error}</p>;
  if (!stats) return <p className="text-sm text-muted">Counting…</p>;

  const { users, chat, feedback, jobs } = stats;
  const sources = Object.entries(users.by_source);
  return (
    <div className="flex flex-col gap-3 pb-6">
      <h1 className="font-display text-xl font-medium">Stats</h1>
      <p className="text-xs text-muted">Excludes {stats.excludes}.</p>
      <Table title="Users" rows={[
        ["Signups", users.signups], ["Last 24 hours", users.signups_24h],
        ["Last 7 days", users.signups_7d], ["Uploaded a resume", users.with_resume],
        ["Active in the last 7 days", users.active_7d],
      ]} />
      <Table title="Signups by source" rows={sources.length ? sources : [["None yet", 0]]} />
      <Table title="Chat" rows={[
        ["Users who chatted", chat.users], ["Messages", chat.messages],
        ["Messages per chatting user", num(chat.messages_per_chat_user)],
        ["Agent turns", chat.agent_turns], ["Valid JSON", pct(chat.json_valid_rate)],
        ["Latency p50", ms(chat.latency_ms_p50)], ["Latency p95", ms(chat.latency_ms_p95)],
        ["Answered by fallback model", pct(chat.fallback_rate)],
      ]} />
      <Table title="Feedback" rows={[
        ["Jobs shown", feedback.shown], ["👍", feedback.likes], ["👎", feedback.dislikes],
        ["Apply clicks", feedback.apply_clicks], ["Shares", feedback.shares],
        ["👍 rate (of shown)", pct(feedback.like_rate)],
        ["Apply rate (of shown)", pct(feedback.apply_rate)],
      ]} />
      <Table title="Jobs" rows={[
        ["Active jobs", jobs.active], ["Companies", jobs.companies],
        ["Last ingest", jobs.last_ingest ? new Date(jobs.last_ingest.started_at).toLocaleString() : "–"],
        ["New in last ingest", jobs.last_ingest?.inserted ?? "–"],
        ["Expired in last ingest", jobs.last_ingest?.expired ?? "–"],
      ]} />
    </div>
  );
}
