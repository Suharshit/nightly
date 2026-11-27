"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";

/** "Delete my data": asks once, deletes the account and everything linked to it, signs out. */
export function DeleteData() {
  const router = useRouter();
  const [step, setStep] = useState<"idle" | "confirm" | "busy">("idle");
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setStep("busy");
    setError(null);
    try {
      await api.deleteMe();
      // The account is gone on the server, so only clear this browser's session.
      await supabase().auth.signOut({ scope: "local" });
      router.replace("/?deleted=1");
    } catch (e) {
      setError((e as Error).message);
      setStep("confirm");
    }
  }

  if (step === "idle") {
    return (
      <button onClick={() => setStep("confirm")} className="self-start text-sm text-muted underline">
        Delete my data
      </button>
    );
  }
  return (
    <div className="text-sm">
      <p>
        This deletes your account, resume, preferences, likes and chat history for good.
        It can&apos;t be undone.
      </p>
      <div className="mt-3 flex gap-2">
        <button onClick={remove} disabled={step === "busy"}
                className="btn btn-primary">
          {step === "busy" ? "Deleting…" : "Delete everything"}
        </button>
        <button onClick={() => setStep("idle")} disabled={step === "busy"} className="btn">
          Cancel
        </button>
      </div>
      {error && <p className="mt-2 text-muted">{error}</p>}
    </div>
  );
}
