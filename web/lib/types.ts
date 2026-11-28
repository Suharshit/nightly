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
  links?: { label: string; panel: string }[];  // extra menu items; only some accounts get any
};

// A view the API builds whole (titles, labels, values); the web app only draws it.
export type PanelView = {
  title: string;
  note?: string;
  tables: { title: string; rows: [string, string][] }[];
  lists: { title: string; aside?: string; empty?: string;
           items: { tags: { text: string; on?: boolean }[]; meta?: string; text: string;
                    foot?: string | null }[] }[];
};

export type Level = "student" | "fresher" | "junior";
export type DislikeReason = "too_senior" | "wrong_location" | "not_interested";
