// Shapes returned by the FastAPI backend (api/app/main.py).

export type Job = {
  id: number;
  title: string;
  company: string;
  city: string | null;
  work_mode: string | null;
  remote: boolean | null;
  seniority: string | null;
  min_exp_years: number | null;
  max_exp_years: number | null;
  skills: string[];
  apply_url: string | null;
  posted_at: string | null;
  reason: string;
};

export type Matches = { q: string; mode: string; count: number; took_ms: number; jobs: Job[] };

export type ChatReply = {
  reply: string;
  jobs: Job[];
  follow_up_chips: string[];
  json_valid: boolean;
  took_ms: number;
  chats_left: number;
};

export type Me = {
  email: string | null;
  has_resume: boolean;
  resume_skills: string[];
  prefs: { roles?: string[]; cities?: string[]; remote?: boolean; level?: string; ref?: string };
};

type Rate = number | null;
export type Stats = {
  users: { signups: number; signups_24h: number; signups_7d: number; with_resume: number;
           active_7d: number; by_source: Record<string, number> };
  chat: { users: number; messages: number; messages_per_chat_user: Rate; agent_turns: number;
          json_valid_rate: Rate; latency_ms_p50: Rate; latency_ms_p95: Rate; fallback_rate: Rate };
  feedback: { shown: number; likes: number; dislikes: number; apply_clicks: number;
              shares: number; like_rate: Rate; apply_rate: Rate };
  jobs: { active: number; companies: number;
          last_ingest: { started_at: string; inserted: number; expired: number } | null };
  excludes: string;
};

export type Level = "student" | "fresher" | "junior";
export type DislikeReason = "too_senior" | "wrong_location" | "not_interested";
