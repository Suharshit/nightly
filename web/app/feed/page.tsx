"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { DeleteData } from "@/components/DeleteData";
import { JobCard } from "@/components/JobCard";
import { Nav } from "@/components/Nav";
import { ApiError, api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { useSession } from "@/lib/useSession";

/** The first matches: built from the resume and saved preferences, no query needed. */
export default function Feed() {
  const router = useRouter();
  const session = useSession();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [fresh, setFresh] = useState<Job[]>([]);   // "New since yesterday"
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setJobs(null);
    const timer = setTimeout(() => setSlow(true), 3000);
    try {
      // The new-jobs section is a bonus: if it fails, the main feed still shows.
      const [feed, latest] = await Promise.all([
        api.feed(), api.newSinceYesterday().catch(() => null),
      ]);
      const freshJobs = latest?.jobs ?? [];
      const freshIds = new Set(freshJobs.map((j) => j.id));
      setFresh(freshJobs);
      setJobs(feed.jobs.filter((j) => !freshIds.has(j.id)));
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

  return (
    <div className="flex flex-col">
      <Nav />
      <div className="mb-3 flex items-baseline justify-between">
        <h1 className="font-display text-xl font-medium">Your matches</h1>
        <button onClick={load} className="text-sm text-muted">Refresh</button>
      </div>

      {error ? (
        <div className="rounded-2xl bg-card p-4 text-sm">
          <p>{error}</p>
          <button onClick={load} className="mt-2 text-accent">Try again</button>
        </div>
      ) : jobs === null ? (
        <p className="text-sm text-muted">
          {slow ? "Waking up the server, this can take up to a minute the first time…" : "Finding jobs…"}
        </p>
      ) : jobs.length === 0 && fresh.length === 0 ? (
        <p className="rounded-2xl bg-card p-4 text-sm">
          Nothing new right now. Try the chat to loosen a filter, like &ldquo;remote is fine too&rdquo;.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {fresh.length > 0 && (
            <section className="flex flex-col gap-3">
              <h2 className="flex items-center gap-2 text-sm font-medium">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent" />
                New since yesterday
              </h2>
              {fresh.map((j) => <JobCard key={j.id} job={j} />)}
              {jobs.length > 0 && <h2 className="mt-2 text-sm font-medium">More matches</h2>}
            </section>
          )}
          {jobs.map((j) => <JobCard key={j.id} job={j} />)}
        </div>
      )}

      {session && (
        <div className="mt-8 flex flex-col">
          <DeleteData />
        </div>
      )}
    </div>
  );
}
