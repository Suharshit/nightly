"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

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
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setJobs(null);
    const timer = setTimeout(() => setSlow(true), 3000);
    try {
      setJobs((await api.feed()).jobs);
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
      ) : jobs.length === 0 ? (
        <p className="rounded-2xl bg-card p-4 text-sm">
          Nothing new right now. Try the chat to loosen a filter, like &ldquo;remote is fine too&rdquo;.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {jobs.map((j) => <JobCard key={j.id} job={j} />)}
        </div>
      )}
    </div>
  );
}
