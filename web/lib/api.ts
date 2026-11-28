"use client";

import { accessToken } from "@/lib/supabase";
import type { ChatReply, DislikeReason, Matches, Me } from "@/lib/types";

// Only `next dev` falls back to a local API. A production build without NEXT_PUBLIC_API_URL
// must not call localhost: that would reach into the visitor's own machine.
const API = (process.env.NEXT_PUBLIC_API_URL
  || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "")).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Exported for pages whose routes must not appear in the shared bundle (see app/stats).
export async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API) throw new ApiError(0, "nightly's server isn't switched on yet. Please check back soon.");
  const token = await accessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { ...init, headers });
  } catch {
    // The free API host sleeps when idle, so the first request can fail or be slow.
    throw new ApiError(0, "Can't reach the server. It may be waking up; try again in a moment.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {}
    throw new ApiError(res.status, detail || `Error ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  me: () => call<Me>("/me"),
  deleteMe: () => call<{ deleted: boolean }>("/me", { method: "DELETE" }),
  feed: () => call<Matches>("/matches?limit=10"),
  newSinceYesterday: () => call<Matches>("/matches?limit=3&new=true"),
  search: (q: string) => call<Matches>(`/matches?limit=5&q=${encodeURIComponent(q)}`),
  chat: (message: string) =>
    call<ChatReply>("/chat", { method: "POST", body: JSON.stringify({ message }) }),
  uploadResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<{ chars: number; skills: string[] }>("/resume", { method: "POST", body: form });
  },
  setPrefs: (prefs: Partial<Me["prefs"]>) =>
    call<{ prefs: Me["prefs"] }>("/prefs", { method: "PATCH", body: JSON.stringify(prefs) }),
  reportBug: (body: { message: string; page?: string; email?: string }) =>
    call<{ id: number }>("/bugs", { method: "POST", body: JSON.stringify(body) }),
  feedback: (job_id: number, action: "like" | "dislike" | "apply_click" | "share",
             reason?: DislikeReason) =>
    call<{ ok: boolean }>("/feedback", {
      method: "POST", body: JSON.stringify({ job_id, action, reason: reason ?? null }),
    }),
};
