"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Mark } from "@/components/Logo";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useSession } from "@/lib/useSession";

/** Land, then sign in with Google or a 6-digit email code (Supabase Auth). */
export default function Landing() {
  const router = useRouter();
  const session = useSession({ required: false });
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"email" | "code">("email");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [deleted, setDeleted] = useState(false);

  // Remember where the visitor came from (?ref=wa_share, wa_group, linkedin) for signup stats.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ref = params.get("ref");
    if (ref && !localStorage.getItem("ref")) localStorage.setItem("ref", ref.slice(0, 32));
    setDeleted(params.get("deleted") === "1");
  }, []);

  // Signed in: onboarding first if there is no resume yet, else the feed.
  useEffect(() => {
    if (!session) return;
    api.me().then((me) => router.replace(me.has_resume ? "/feed" : "/onboard"),
                  () => router.replace("/onboard"));
  }, [session, router]);

  async function google() {
    setError(null);
    const { error } = await supabase().auth.signInWithOAuth({
      provider: "google", options: { redirectTo: `${window.location.origin}/` },
    });
    if (error) setError(error.message);
  }

  async function sendCode(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabase().auth.signInWithOtp({
      email: email.trim(), options: { shouldCreateUser: true },
    });
    setBusy(false);
    if (error) setError(error.message);
    else setStep("code");
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabase().auth.verifyOtp({
      email: email.trim(), token: code.trim(), type: "email",
    });
    setBusy(false);
    if (error) setError(error.message);
  }

  if (session) return <p className="page text-muted">Signing you in…</p>;

  const facts = [["Every night", "new jobs"], ["Fresher", "filters"], ["A reason", "for each match"]];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-1 flex-col gap-4 px-4 py-4">
        {deleted && (
          <p role="status" className="box px-4 py-3 text-sm">
            Your account and all your data are deleted.
          </p>
        )}
        <section className="box flex flex-col">
          <div className="flex items-center justify-between border-b border-text px-4 py-2 text-xs text-muted">
            <span>Startup jobs for Indian students and freshers</span>
            <span>Free</span>
          </div>
          <div className="px-4 py-6">
            <div className="mb-5 text-text"><Mark size={44} /></div>
            <h1 className="font-display text-3xl font-medium leading-tight tracking-tight">
              Wake up to a short list of jobs you can actually apply for.
            </h1>
            <p className="mt-3 text-sm text-muted">
              nightly reads startup job boards every night and matches them to your resume,
              one job at a time.
            </p>
          </div>
          <dl className="grid grid-cols-3 border-t border-text text-sm">
            {facts.map(([a, b], i) => (
              <div key={a} className={`px-3 py-3 ${i ? "border-l border-text" : ""}`}>
                <dt className="font-medium">{a}</dt>
                <dd className="text-xs text-muted">{b}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="box flex flex-col gap-3 p-4">
          <h2 className="font-display text-base font-medium">Sign in</h2>
          <button onClick={google} className="btn btn-primary w-full">Continue with Google</button>

          <div className="flex items-center gap-3 text-xs text-muted">
            <span className="h-px flex-1 bg-text/40" /> or use your email <span className="h-px flex-1 bg-text/40" />
          </div>

          {step === "email" ? (
            <form onSubmit={sendCode} className="flex">
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                     placeholder="you@college.edu" autoComplete="email" aria-label="Email"
                     className="field flex-1 border-r-0" />
              <button disabled={busy} className="btn">{busy ? "…" : "Send code"}</button>
            </form>
          ) : (
            <form onSubmit={verify} className="flex flex-col gap-2">
              <p className="text-sm text-muted">We sent a 6-digit code to {email}.</p>
              <div className="flex">
                <input inputMode="numeric" autoComplete="one-time-code" required value={code}
                       onChange={(e) => setCode(e.target.value)} placeholder="123456" maxLength={6}
                       aria-label="Code" className="field flex-1 border-r-0 tracking-widest" />
                <button disabled={busy} className="btn">{busy ? "…" : "Verify"}</button>
              </div>
              <button type="button" onClick={() => setStep("email")}
                      className="self-start text-sm text-muted underline">
                Use a different email
              </button>
            </form>
          )}
          {error && <p className="text-sm text-muted">{error}</p>}
        </section>
      </div>
      <footer className="flex justify-center gap-4 border-t border-text px-4 py-3 text-xs text-muted">
        <Link href="/privacy" className="underline">Privacy</Link>
        <Link href="/bug" className="underline">Report a bug</Link>
      </footer>
    </div>
  );
}
