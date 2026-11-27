"use client";

import { useEffect, useRef, useState } from "react";

import { JobCard } from "@/components/JobCard";
import { Nav } from "@/components/Nav";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { useSession } from "@/lib/useSession";

type Message = { role: "user" | "assistant"; text: string; jobs?: Job[]; chips?: string[] };

const STARTERS = ["Anything with Go?", "Only remote from now on", "Why not senior roles?"];

/** Refine in plain language; the agent answers with a short reply, cards and next steps. */
export default function Chat() {
  const session = useSession();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  // Braces matter: newer Chrome returns a Promise from scrollIntoView, and an effect that returns
  // it hands React a "cleanup" that is not a function (crash: "n is not a function").
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: message }]);
    setBusy(true);
    try {
      const r = await api.chat(message);
      setMessages((m) => [...m, { role: "assistant", text: r.reply, jobs: r.jobs, chips: r.follow_up_chips }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: (e as Error).message }]);
    } finally {
      setBusy(false);
    }
  }

  if (session === undefined) return null;
  const last = messages[messages.length - 1];
  const chips = !messages.length ? STARTERS : last?.role === "assistant" ? last.chips ?? [] : [];

  return (
    <div className="flex flex-1 flex-col">
      <Nav />
      <div className="flex flex-1 flex-col gap-3 pb-4">
        {!messages.length && (
          <p className="text-sm text-muted">Ask for what you want: a stack, a city, remote, a level.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "self-end max-w-[85%]" : "flex flex-col gap-3"}>
            <p className={`rounded-2xl px-4 py-2.5 text-sm ${m.role === "user" ? "bg-primary text-on-primary" : "bg-card"}`}>
              {m.text}
            </p>
            {m.jobs?.map((j) => <JobCard key={j.id} job={j} />)}
          </div>
        ))}
        {busy && <p className="text-sm text-muted">Looking…</p>}
        <div ref={end} />
      </div>

      <div className="sticky bottom-0 bg-bg pb-3 pt-2">
        {chips.length > 0 && !busy && (
          <div className="mb-2 flex gap-2 overflow-x-auto">
            {chips.map((c) => (
              <button key={c} onClick={() => send(c)}
                      className="shrink-0 rounded-full border border-line px-3 py-1.5 text-sm">
                {c}
              </button>
            ))}
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={500}
                 placeholder="e.g. remote python internships"
                 className="min-w-0 flex-1 rounded-full border border-line bg-card px-4 py-3 text-sm placeholder:text-muted" />
          <button disabled={busy || !input.trim()}
                  className="rounded-full bg-primary px-4 py-3 text-sm font-medium text-on-primary disabled:opacity-40">
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
