"use client";

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

  if (session) return <p className="text-muted">Signing you in…</p>;

  return (
    <div className="flex flex-1 flex-col justify-center gap-8 pb-10">
      {deleted && (
        <p role="status" className="rounded-2xl bg-card px-4 py-3 text-sm">
          Your account and all your data are deleted.
        </p>
      )}
      <section>
        <div className="mb-6 text-text"><Mark size={48} /></div>
        <h1 className="font-display text-3xl font-medium leading-tight tracking-tight">
          Wake up to 3 startup jobs worth applying for.
        </h1>
        <p className="mt-3 text-muted">
          nightly reads startup job boards every night and matches them to your resume.
          Fresher-friendly filters, a reason for every match, free.
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <button onClick={google}
                className="rounded-full bg-primary px-4 py-3 font-medium text-on-primary">
          Continue with Google
        </button>

        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="h-px flex-1 bg-line" /> or use your email <span className="h-px flex-1 bg-line" />
        </div>

        {step === "email" ? (
          <form onSubmit={sendCode} className="flex gap-2">
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                   placeholder="you@college.edu" autoComplete="email"
                   className="min-w-0 flex-1 rounded-full border border-line bg-card px-4 py-3 placeholder:text-muted" />
            <button disabled={busy} className="rounded-full border border-line px-4 py-3 font-medium">
              {busy ? "…" : "Send code"}
            </button>
          </form>
        ) : (
          <form onSubmit={verify} className="flex flex-col gap-2">
            <p className="text-sm text-muted">We sent a 6-digit code to {email}.</p>
            <div className="flex gap-2">
              <input inputMode="numeric" autoComplete="one-time-code" required value={code}
                     onChange={(e) => setCode(e.target.value)} placeholder="123456" maxLength={6}
                     className="min-w-0 flex-1 rounded-full border border-line bg-card px-4 py-3 tracking-widest placeholder:text-muted" />
              <button disabled={busy} className="rounded-full border border-line px-4 py-3 font-medium">
                {busy ? "…" : "Verify"}
              </button>
            </div>
            <button type="button" onClick={() => setStep("email")} className="self-start text-sm text-muted">
              Use a different email
            </button>
          </form>
        )}
        {error && <p className="text-sm text-muted">{error}</p>}
      </section>
    </div>
  );
}
