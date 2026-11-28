"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useSession } from "@/lib/useSession";

const PLACES = ["Matches", "Chat", "Sign in", "Setup", "Other"];

/** Report a bug from inside the app, no GitHub account needed. The owner sees it in their stats view. */
export default function ReportBug() {
  const session = useSession({ required: false });
  const [message, setMessage] = useState("");
  const [where, setWhere] = useState(PLACES[0]);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ?from=chat (etc.) picks where it happened; a signed-in email is offered for replies.
  useEffect(() => {
    const from = (new URLSearchParams(window.location.search).get("from") || "").toLowerCase();
    const match = PLACES.find((p) => from && p.toLowerCase().startsWith(from));
    if (match) setWhere(match);
  }, []);
  useEffect(() => {
    if (session?.user.email) setEmail((e) => e || session.user.email || "");
  }, [session]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const page = `${where} · ${window.innerWidth}×${window.innerHeight}`;
      const r = await api.reportBug({ message: message.trim(), page,
                                      email: email.trim() || undefined });
      setDone(r.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (done !== null) {
    return (
      <div className="page">
        <div className="box flex flex-col gap-3 p-5">
          <h1 className="font-display text-xl font-medium">Thanks, got it.</h1>
          <p className="text-sm text-muted">
            Logged as bug #{done}.{email ? " We may email you if we need more detail." : ""}
          </p>
          <div className="flex gap-2">
            <Link href={session ? "/feed" : "/"} className="btn btn-primary">Back to nightly</Link>
            <button className="btn" onClick={() => { setDone(null); setMessage(""); }}>
              Report another
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="page gap-5">
      <div>
        <h1 className="font-display text-2xl font-medium">Report a bug</h1>
        <p className="mt-1 text-sm text-muted">
          Something broken or confusing? Tell us here. No GitHub account needed.
        </p>
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">What went wrong?</span>
        <textarea required minLength={5} maxLength={2000} rows={6} value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="What you did, what you expected, and what happened instead."
                  className="field resize-y" />
        <span className="self-end text-xs tabular-nums text-muted">{message.length} / 2000</span>
      </label>

      <fieldset>
        <legend className="mb-2 text-sm font-medium">Where?</legend>
        <div className="flex flex-wrap gap-2">
          {PLACES.map((p) => (
            <button type="button" key={p} aria-pressed={where === p} onClick={() => setWhere(p)}
                    className={`btn px-3 py-1.5 ${where === p ? "btn-primary" : ""}`}>
              {p}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">
          Email <span className="font-normal text-muted">(optional, only to reply)</span>
        </span>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
               maxLength={200} placeholder="you@college.edu" autoComplete="email"
               className="field" />
      </label>

      <p className="text-xs text-muted">
        We also save your screen size and browser name, to help us reproduce it.{" "}
        <Link href="/privacy" className="underline">Privacy</Link>
      </p>
      {error && <p className="text-sm text-muted">{error}</p>}
      <button disabled={message.trim().length < 5 || busy} className="btn btn-primary">
        {busy ? "Sending…" : "Send report"}
      </button>
    </form>
  );
}
