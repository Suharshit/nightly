# nightly: build brief for Claude Code

Last updated: 25 Nov 2026 · Owner: Suharshit Singh

## Goal and definition of done

Ship a live, mobile-first job-matching web app for Indian students and freshers by **Sunday 29 Nov 2026, 11:59 pm IST**. It must have real users and measured search and agent quality, so it can go on a resume for the Elip SDE Intern drive.

The app (**product name nightly**) pulls jobs from public startup job boards every night. It learns what each user wants through chat and their resume, and shows the best matches with a reason for each. It improves from 👍/👎 feedback and emails each user 3 fresh matches every morning.

**Done means all of these are true on Sunday night:**

1. A public URL works on a phone: sign in, upload a resume, chat, see matches, give feedback, and share a job on WhatsApp.
2. The index holds at least 1,500 active jobs from at least 100 companies, refreshed by a nightly job that runs without anyone touching it.
3. `eval/` prints a results table: search NDCG@10 for keyword, vector, hybrid and hybrid+rerank; agent tool-call accuracy; JSON validity rate; extraction accuracy per field.
4. At least 30 real users have signed up, with usage logged (users, chats, feedback events).
5. The README holds the architecture, the eval table, real usage numbers, a 2-minute demo video link and run instructions. The repo is public on GitHub.

**Total time available:** Wed afternoon to Sun night, at 8–10 focused hours a day (about 40–48 hours). That is about 4.5 days, not a full week, so scope is fixed and the cut order (see Risks) is part of the plan.

## Hard constraints

The budget is ₹0 and only open-weight models are allowed. Any choice that needs a card, a paid tier or a closed model is out.

- **LLMs:** open-weight models only, called through Groq's free tier (OpenAI-compatible API), with local Ollama as the fallback. Default models are `openai/gpt-oss-120b` or `llama-3.3-70b-versatile` for the agent and `llama-3.1-8b-instant` for extraction. Free-tier limits are per model. For gpt-oss-120b they are 30 requests/min, 1,000 requests/day, 8,000 tokens/min and 200,000 tokens/day ([benchlm, read 2026-09-14](https://benchlm.ai/md/free-tier/groq.md)). Read the real limits from the Groq console on day 1 and design around them.
- **Embeddings and reranking:** run locally on CPU with sentence-transformers, so there is no per-call cost.
- **Infra:** free tiers only (Supabase, Hugging Face Spaces, Vercel, GitHub Actions on a public repo, Gmail SMTP). Never add a payment method.
- **Data:** use only public job-board APIs that companies publish for their own career pages. No scraping LinkedIn, Naukri or Indeed. Respect each provider's terms and rate limits.
- **Privacy:** resumes are personal data. Store them only to make matches, show a one-line privacy note at upload, and give a "delete my data" button that really deletes.
- **Honesty:** every number in the README and on the resume comes from logs or eval scripts. Nothing is estimated or invented.

## Product and user flow

One user, one loop: tell it what you want, get 3 good matches with reasons, react, and get better matches tomorrow. It is a small version of what Elip does, scoped to Indian startup jobs for students and freshers.

1. **Land:** the user opens a link shared in a WhatsApp group or on LinkedIn. The page says what it does in one line and shows a live count of jobs indexed.
2. **Sign in:** Google sign-in or email OTP through Supabase Auth.
3. **Onboard (under 60 s):** upload a resume PDF, then answer 3 quick chips: role type, location (city or remote), experience (student / fresher / 1–2 yrs). The resume is parsed and embedded, and preferences are saved.
4. **First matches:** 3 to 5 job cards appear right away. Each shows title, company, location, posted date and a one-line "why this fits you" reason, plus 👍 / 👎 / Apply / Share on WhatsApp.
5. **Chat:** the user refines in plain language, e.g. "anything with Go?", "only remote", "why not senior roles?". The agent calls tools and answers with cards and reasons.
6. **Feedback:** each 👍 / 👎 is stored and changes that user's next ranking. A 👎 asks one optional reason chip (too senior, wrong location, not interested in the domain).
7. **Daily digest:** at 8:00 IST, an email with 3 new matches the user has not seen, each linking back to the app.

Out of scope this week: applying on the user's behalf, resume tailoring, recruiter side, payments, native mobile apps, and a WhatsApp bot (see the next section).

## Channel: a mobile-first web app, spread through WhatsApp links

Decision: build a mobile-first web app (installable as a PWA), not a Telegram bot. Use WhatsApp for distribution, not as the interface. Indian students live on WhatsApp, so every job card gets a "Share on WhatsApp" button (`https://wa.me/?text=...` with the job and the app link). Launch posts go into WhatsApp groups. Nobody has to install anything.

| Option | Reach in India | Cost at ₹0 | Time to ship | Verdict |
| --- | --- | --- | --- | --- |
| Telegram bot | Low for this audience | Free | Fast | Dropped |
| WhatsApp Cloud API bot | Highest | Replies free only within limits; morning digests are paid templates | Slow: Meta business setup and a dedicated number | Stretch goal after Sunday |
| Mobile web app + WhatsApp share links | High, opens from any WhatsApp chat | Free | Fast | **Build this** |

Why not the WhatsApp API this week: since 1 Oct 2026, service replies are free only up to 1,000 per business number per month, then ₹0.145 each in India, and marketing messages cost about ₹1.09 each ([AiSensy pricing guide](https://m.aisensy.com/blog/whatsapp-business-pricing/); [Meta pricing docs](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)). A daily digest is business-initiated, so it would cost money. Setup also eats a day that the core system needs.

Keep the agent independent of the channel (`agent.respond(user_id, message) -> AgentReply`). Adding a WhatsApp or Telegram adapter later is then about a day of work. That makes a good interview talking point.

## Brand: nightly

The product is called **nightly** (always lowercase), with the descriptor "nightly · startup jobs for freshers" and the tagline "Wake up to 3 startup jobs worth applying for." The theme is minimal: neutral greys, one accent, one mark, and both a day and a night theme. Spend at most 1 hour on branding.

**Themes.** The app ships a light (day) theme and a dark (night) theme. The default follows the device (`prefers-color-scheme`). A sun/moon toggle in the header overrides it and is saved in `localStorage`. Build it with CSS variables plus Tailwind `darkMode: 'class'` and the semantic tokens below. Components never use raw hex values.

| Token | Day (light) | Night (dark) | Use |
| --- | --- | --- | --- |
| `bg` | `#FFFFFF` | `#0A0A0B` | Page background |
| `card` | `#F7F7F5` | `#16161A` | Cards, inputs, chat bubbles |
| `line` | `#E5E5E2` | `#26262B` | Borders, dividers, secondary buttons |
| `muted` | `#6B6B73` | `#8A8A93` | Meta text, placeholders |
| `text` | `#0A0A0B` | `#F4F4F2` | Main text, logo arch |
| `primary` | `#0A0A0B` | `#C6FF3D` | Primary button fill (Apply, Continue) |
| `on-primary` | `#FFFFFF` | `#0A0A0B` | Text on the primary button |
| `accent` | `#4D7C0F` | `#C6FF3D` | Logo dot, "new" dot, links, focus ring, match highlights |

**Rules:** the accent covers about 5% of any screen at most. Never put `#C6FF3D` on a light background, as text or as a dot; use `#4D7C0F` there. The email digest always uses the day theme. Check contrast (WCAG AA) for `muted` and `accent` text on both backgrounds before shipping.

**Type:** Space Grotesk 500 for the wordmark and headings; Inter 400/500 for everything else. Both are free on Google Fonts, loaded via `next/font`.

**Logo:** a lowercase "n" arch (a horizon) with one dot at the top right (the moon, or a new match). Day version: arch `#0A0A0B`, dot `#4D7C0F`. Night version: arch `#F4F4F2`, dot `#C6FF3D`. The wordmark is "nightly" in Space Grotesk 500, followed by a dot in the same colour as the mark's dot, with the mark on its left. Build it as one theme-aware component:

```svg
<!-- logo mark: arch uses currentColor (= text token), dot uses the accent token -->
<svg viewBox="22 14 66 68" xmlns="http://www.w3.org/2000/svg" aria-label="nightly">
  <path d="M32 76V48a18 18 0 0 1 36 0v28" fill="none" stroke="currentColor" stroke-width="12" stroke-linecap="round"/>
  <circle cx="78" cy="24" r="7" fill="var(--accent)"/>
</svg>
```

The app icon and favicon use the night version on a tile, so they work on any home screen:

```svg
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="100" rx="22" fill="#0A0A0B"/>
  <path d="M32 76V48a18 18 0 0 1 36 0v28" fill="none" stroke="#F4F4F2" stroke-width="12" stroke-linecap="round"/>
  <circle cx="78" cy="24" r="7" fill="#C6FF3D"/>
</svg>
```

Exports to generate: `logo-day.svg`, `logo-night.svg`, `icon.svg`, `icon-192.png` and `icon-512.png` (PWA manifest), and `favicon-32.png`.

## Architecture, stack and repo layout

Three deployables share one Postgres: a Next.js frontend, a Python FastAPI backend that runs search and the agent, and scheduled Python jobs for ingestion and the digest. Python on the backend matches the JD ("Python backends").

```text
NIGHTLY (GitHub Actions cron)            LIVE (every request)

Greenhouse/Lever/Ashby APIs              Phone browser (Next.js on Vercel)
        |                                        |  Supabase JWT
        v                                        v
worker/ingest.py                         api/ FastAPI (HF Space, Docker)
  fetch -> normalise -> dedupe             /chat   -> agent loop (Groq LLM + tools)
  -> extract (8B LLM, JSON)                /matches -> search + rank
  -> embed (bge-small, CPU)                /feedback, /resume, /me, /delete
        |                                        |
        +--------------> Supabase Postgres <-----+
                         (pgvector + full-text + auth)

worker/digest.py (cron 02:30 UTC = 08:00 IST) -> Gmail SMTP -> users
```

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | Next.js 14 App Router + Tailwind, on Vercel free | You already shipped Vibely on this stack |
| Auth | Supabase Auth (Google + email OTP) | Free; the FastAPI side verifies the JWT |
| Backend | FastAPI + Pydantic v2, Python 3.11, Docker | JD wants Python backends; you already know FastAPI and Pydantic from VeriFaith |
| Database | Supabase Postgres with `pgvector` and `tsvector` | One store for jobs, vectors, users and logs; SQL is a JD skill |
| LLM | Groq free tier, open-weight models; Ollama fallback | Rules: ₹0, open weights only |
| Embeddings | `BAAI/bge-small-en-v1.5` (384-d) | Small, strong, fast on CPU |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2`; try `BAAI/bge-reranker-base` if latency allows | Small enough for a free CPU host |
| API hosting | Hugging Face Spaces, Docker, free CPU | Enough RAM to hold both models; it sleeps when idle, so the first request is slow |
| Scheduler | GitHub Actions cron on a public repo | Free; runs ingest and digest |
| Email | Gmail SMTP with an app password | Free for a few hundred mails a day |

Check each free tier's current limits before relying on it. If HF Spaces won't fit, try Render's free tier and the smaller reranker.

**Repo layout (monorepo):**

```text
nightly/
  web/                 Next.js app
  api/
    app/main.py        FastAPI routes
    app/agent/         loop.py, tools.py, prompts.py, schemas.py
    app/search/        hybrid.py, rerank.py, personalise.py
    app/db.py          asyncpg pool + queries
    app/models.py      loads embedder + reranker once at startup
    Dockerfile
  worker/
    sources/           greenhouse.py, lever.py, ashby.py (one adapter each)
    ingest.py  extract.py  embed.py  digest.py
  db/migrations/       001_init.sql ...
  data/companies.csv   name, ats, slug, city
  eval/                queries.jsonl, convos.jsonl, extraction.jsonl, run_*.py, results.md
  .github/workflows/   ingest.yml, digest.yml, ci.yml
  docker-compose.yml   local Postgres+pgvector, api, worker
  CLAUDE.md  README.md  .env.example
```

## Data sources and nightly ingestion

Pull from the public job-board APIs that startups use for their own careers pages. Each company is identified by an ATS name and a board slug kept in `data/companies.csv`. The endpoints below are the commonly used public ones. **Claude Code must confirm each against the provider's current docs before writing the adapter.**

| ATS | Endpoint pattern (verify) | Notes |
| --- | --- | --- |
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | Description comes as HTML; has location and updated\_at |
| Lever | `https://api.lever.co/v0/postings/{slug}?mode=json` | Has categories (team, location, commitment) |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | Often includes salary |

**Company list.** Target 100–150 Indian startups (YC India, funded Bengaluru, Gurugram and Pune companies) whose careers page is on one of these three. Find a slug from the careers page URL (e.g. `jobs.lever.co/{slug}`). Write a `scripts/check_slugs.py` that drops slugs returning 404 or zero jobs. Keep only jobs located in India or marked remote.

**Pipeline steps (`worker/ingest.py`, idempotent, safe to re-run):**

1. **Fetch** every board with a polite client: 1 request/second, retries with backoff, a User-Agent with a contact email.
2. **Normalise** each source into one Pydantic `JobIn` model: `source, external_id, company, title, location_raw, remote, description_text` (HTML stripped), `apply_url, posted_at, salary_raw`.
3. **Upsert** on `UNIQUE(source, external_id)`. Set `last_seen = now()`. Compute `content_hash = sha256(title + description_text)`.
4. **Changed-only work:** if `content_hash` changed or the row is new, set `extraction_status='pending'` and `embedding=NULL`.
5. **Expire:** any active job with `last_seen` older than 36 hours becomes `is_active=false`. This handles listings that disappear.
6. **Dedupe:** the same company with near-identical titles (normalised, or embedding cosine > 0.95) across sources gets a shared `canonical_id`. Search returns only canonical rows.
7. **Extract (`extract.py`):** for pending rows, send the first \~1,500 characters of the description to the 8B model. Request JSON output validated by Pydantic: `skills[]` (lowercase, max 12), `min_exp_years`, `max_exp_years`, `seniority` (intern / fresher / junior / mid / senior), `employment_type`, `work_mode` (onsite / hybrid / remote), `city`, `salary_min_inr`, `salary_max_inr` (null if unknown). On a validation failure, retry once, then mark `failed`. Use a token-bucket limiter set from the real Groq limits. The job is resumable, so a daily cap just carries the rest over to tomorrow.
8. **Embed (`embed.py`):** text = `title | company | city | work_mode | skills | first 800 chars of description` → bge-small → `embedding vector(384)`, normalised. Batch 64 at a time on CPU.
9. **Log** a run summary row in `ingest_runs`: fetched, new, updated, expired, extracted, failed, duration.

**Backfill tip:** the first full extraction may exceed the free LLM limits. Run it locally with Ollama (e.g. a 3B–8B open model) on the laptop on day 1. After that, nightly runs only touch new and changed jobs, which is a small number.

## Postgres schema and indexes

Six core tables plus two log tables. Write them as `db/migrations/001_init.sql`. Be ready to explain every index in an interview, since "designing tables and queries for a real system" is one of Elip's screening points.

```sql
create extension if not exists vector;
create extension if not exists pg_trgm;

create table companies (
  id serial primary key,
  name text not null,
  ats text not null check (ats in ('greenhouse','lever','ashby')),
  slug text not null,
  city text,
  unique (ats, slug)
);

create table jobs (
  id bigserial primary key,
  company_id int not null references companies(id),
  source text not null,
  external_id text not null,
  canonical_id bigint references jobs(id),
  title text not null,
  location_raw text,
  city text,
  work_mode text,               -- onsite | hybrid | remote
  seniority text,               -- intern | fresher | junior | mid | senior
  min_exp_years int,
  max_exp_years int,
  skills text[] default '{}',
  salary_min_inr int,
  salary_max_inr int,
  description_text text,
  apply_url text,
  posted_at timestamptz,
  first_seen timestamptz default now(),
  last_seen timestamptz default now(),
  is_active boolean default true,
  content_hash text,
  extraction_status text default 'pending',  -- pending | done | failed
  embedding vector(384),
  tsv tsvector generated always as (
    setweight(to_tsvector('english', coalesce(title,'')), 'A') ||
    setweight(to_tsvector('english', array_to_string(skills,' ')), 'B') ||
    setweight(to_tsvector('english', coalesce(description_text,'')), 'C')
  ) stored,
  unique (source, external_id)
);
create index jobs_active_idx on jobs (is_active, posted_at desc) where is_active;
create index jobs_tsv_idx on jobs using gin (tsv);
create index jobs_emb_idx on jobs using hnsw (embedding vector_cosine_ops);
create index jobs_skills_idx on jobs using gin (skills);

create table profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text,
  resume_text text,
  resume_embedding vector(384),
  prefs jsonb default '{}',     -- roles, cities, work_mode, seniority, must_skills, avoid
  taste_embedding vector(384),  -- running mean of liked jobs
  digest_opt_in boolean default true,
  created_at timestamptz default now()
);

create table interactions (
  id bigserial primary key,
  user_id uuid references profiles(user_id) on delete cascade,
  job_id bigint references jobs(id),
  action text check (action in ('shown','like','dislike','apply_click','share')),
  reason text,
  created_at timestamptz default now()
);
create index interactions_user_idx on interactions (user_id, created_at desc);

create table messages (          -- short-term chat memory
  id bigserial primary key,
  user_id uuid references profiles(user_id) on delete cascade,
  role text, content text, tool_calls jsonb,
  created_at timestamptz default now()
);

create table digests_sent (
  user_id uuid references profiles(user_id) on delete cascade,
  job_id bigint references jobs(id),
  sent_on date,
  primary key (user_id, job_id)
);

create table agent_logs (        -- metrics for README and evals
  id bigserial primary key, user_id uuid, model text,
  latency_ms int, prompt_tokens int, completion_tokens int,
  tool_calls jsonb, json_valid boolean, error text,
  created_at timestamptz default now()
);

create table ingest_runs (
  id serial primary key, started_at timestamptz, finished_at timestamptz,
  fetched int, inserted int, updated int, expired int,
  extracted int, failed int, notes text
);
```

Turn on Row Level Security for `profiles`, `interactions` and `messages`, so a user can only read their own rows. This is the same pattern as Vibely. The API uses the service role key on the server only.

## Search, reranking and personalisation

Search runs in four stages. Each stage can be switched off by a flag, so the eval can compare them: filter, retrieve two ways, fuse, rerank, personalise. Target p95 latency for `/matches` is under 1.5 s on a warm host.

1. **Hard filter (SQL `WHERE`):** `is_active`, canonical rows only, `city = ANY(prefs.cities) OR work_mode='remote'` when the user asked for it, and a seniority/experience match (a fresher never sees `senior`). Also exclude jobs already disliked or shown 3+ times.
2. **Retrieve about 50 + 50 candidates:**
   - Keyword: `ts_rank_cd(tsv, websearch_to_tsquery('english', :q))`, top 50. This catches exact tech words like Go, Kafka or React Native.
   - Vector: `embedding <=> :query_vec`, top 50. The query vector is the chat query, or the resume embedding when there is no query. This catches meaning, e.g. "backend" matching "server-side".
3. **Fuse with reciprocal rank fusion:** `rrf(d) = Σ 1 / (60 + rank_i(d))` across both lists. Keep the top 30. No tuning needed.
4. **Rerank** the top 30 with the cross-encoder on (query text, job text). For a query-less feed, the query text is a short summary of the profile built from prefs and the resume's top skills.
5. **Personalise** to get the final score:

```text
score = 1.0 * rerank_norm
      + 0.3 * cos(job.embedding, profile.taste_embedding)   # liked-jobs centroid
      + 0.2 * skill_overlap(job.skills, resume_skills)      # Jaccard
      + 0.1 * freshness                                     # exp(-days_since_posted / 14)
      - 0.5 * disliked_pattern_penalty                      # same company or seniority as recent dislikes
```

Start with these weights, then tune them once against the labelled queries. Don't hand-tweak them per query.

**Diversity:** at most 2 jobs per company in any list of 5.

**Reasons ("why this fits you"):** build them from data, not free LLM text. Use matched skills, the location match, experience fit and freshness, e.g. "Matches your Python + SQL · Remote · Fresher-friendly · Posted 2 days ago". The agent may rephrase this, but only from these facts. That keeps reasons truthful and cheap.

**Feedback updates:** a like moves `taste_embedding` 20% toward the job, using a normalised moving average. A dislike with a reason updates `prefs.avoid`, e.g. `{seniority: ['mid']}`. Every card render logs a `shown` interaction.

## Agent: tools, memory and structured outputs

The agent is a plain tool-calling loop over Groq's OpenAI-compatible chat API. Don't use a framework: the loop is about 80 lines, and an interviewer can follow every step. It never invents a job. Every job it mentions must come from a tool result, and the server checks this.

**Loop (`api/app/agent/loop.py`):**

1. Load context: system prompt + profile summary (prefs, top resume skills, recent dislikes) + the last 10 `messages`.
2. Call the LLM with the tools below. If it returns tool calls, run them, add the results and call again. Stop at 4 tool rounds.
3. The final answer must be JSON matching `AgentReply` (Pydantic): `{"reply": str, "job_ids": [int], "reasons": {job_id: str}, "follow_up_chips": [str]}`. If it fails validation, re-ask once with the error. If it fails again, fall back to a plain reply and log `json_valid=false`.
4. **Guardrail:** drop any `job_id` that was not returned by a tool in this turn.
5. Write the user and assistant messages to `messages` and a row to `agent_logs` (model, latency, tokens, tools, json\_valid).
6. On a Groq 429, retry once with backoff, then fall back to the 8B model, and log the fallback.

**Tools (JSON Schema, in `tools.py`):**

| Tool | Arguments | Does |
| --- | --- | --- |
| `search_jobs` | `query?, cities?, work_mode?, seniority?, skills?, limit<=5` | Runs the full search pipeline for this user; returns compact job cards with data-built reasons |
| `get_job` | `job_id` | Full details of one job (for "tell me more") |
| `update_prefs` | `field, value, op: set/add/remove` | Saves long-term preferences, e.g. "only remote from now on" |
| `record_feedback` | `job_id, action, reason?` | Same effect as tapping 👍/👎 in chat |
| `explain_match` | `job_id` | Returns the matched and missing skills and the fit facts used for a reason |

**Memory:** short-term memory is the last 10 messages. Long-term memory is `profiles.prefs`, `taste_embedding` and the interaction history. Long-term memory persists across days and is the only place preferences live, so the agent must call `update_prefs` instead of "remembering" in text.

**System prompt rules (`prompts.py`):** you help Indian students find startup jobs; always call `search_jobs` before recommending; at most 5 jobs per reply; reasons come only from tool facts; ask at most one clarifying question; if nothing matches, say so and suggest loosening one filter; keep replies under 80 words.

**Model choice:** `openai/gpt-oss-120b` or `llama-3.3-70b-versatile` for the loop. Compare both on the agent eval and keep the better one. Record the choice and the numbers in the README.

## Evals and metrics

The eval table is the most valuable thing on the resume: it turns "I built a job bot" into "I measured what each stage adds." Each eval is one script that writes into `eval/results.md`.

**Freeze a snapshot first.** The index changes every night, so copy the active jobs into `jobs_eval_snapshot` once (Friday). Run every search eval against that snapshot, so the numbers stay comparable.

| Eval | Data (hand-labelled by me, not by an LLM) | Metrics | Compare |
| --- | --- | --- | --- |
| Search | `queries.jsonl`: 40–50 queries, each with graded labels (2 = great, 1 = ok, 0 = no) on the pooled top 20 from all variants | NDCG@10, Recall@50, MRR | keyword only · vector only · hybrid RRF · hybrid + rerank · + personalisation |
| Personalisation | 5 simulated users: a profile + 5 likes and 5 dislikes; held-out liked jobs | Hit@5 of held-out likes | with vs without the taste and dislike terms |
| Agent | `convos.jsonl`: 30–40 scripted turns with the expected tool and key arguments | tool-selection accuracy, argument accuracy, JSON-valid rate, hallucinated-job rate (should be 0), p50/p95 latency | gpt-oss-120b vs llama-3.3-70b |
| Extraction | `extraction.jsonl`: 50 job descriptions with true fields | per-field accuracy (skills as F1), JSON-valid rate, tokens per job | 8B vs 70B |

**Labelling method (write this in the README):** pool the top 20 results from every variant for each query, shuffle them, hide which variant produced each, and label them in a small CLI (`eval/label.py`). Claude Code can build the labeller and propose queries. The labels themselves are mine.

**Live product metrics** come from `agent_logs`, `interactions` and `profiles`: signups, weekly active users, chats per user, 👍 rate on shown jobs, apply-click rate, shares, digest open/click via a tracked redirect link. Show them on a tiny `/stats` admin page and copy the final numbers into the README on Sunday night.

## Deploy, config and ops

Everything runs locally with `docker compose up` first, then deploys to free tiers. Secrets live only in `.env` (git-ignored) and in each platform's secret store.

**Environment variables (`.env.example`):** `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` (or the JWKS URL), `GROQ_API_KEY`, `AGENT_MODEL`, `EXTRACT_MODEL`, `EMBED_MODEL=BAAI/bge-small-en-v1.5`, `RERANK_MODEL`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `APP_BASE_URL`, `ADMIN_EMAILS`.

**Deploy targets:**

- **API:** Hugging Face Space (Docker SDK). The Dockerfile downloads both models at build time, so cold starts don't fetch them. It loads the models once at startup and exposes `/health`.
- **Web:** Vercel, with `NEXT_PUBLIC_API_URL` pointing at the Space.
- **DB:** Supabase free project. Apply migrations with `psql` or the Supabase SQL editor.
- **Cron:** `.github/workflows/ingest.yml` runs nightly at 20:30 UTC (02:00 IST) and runs `worker/ingest.py && extract.py && embed.py`. `digest.yml` runs at 02:30 UTC (08:00 IST). Cache the Hugging Face model folder between runs.
- **CI:** `ci.yml` runs `ruff` + `pytest` on every push.

**Tests that matter (keep it lean):** one parser test per ATS adapter, with a saved JSON fixture; RRF fusion; the personalisation score; `AgentReply` validation; the guardrail that drops unseen job IDs; an idempotent re-run of ingest (a second run inserts 0 rows).

**Ops basics:** structured JSON logs, `/health`, CORS locked to the Vercel domain, and per-user rate limits (e.g. 30 chat messages per day per user, which protects the Groq quota). The "delete my data" button cascades through `profiles`.

## Day-by-day plan (Wed 25 → Sun 29 Nov)

The order is chosen so that something demo-able exists every night: data first, then search, then the agent and UI, then launch. Claude Code should split each day into tasks of 1–2 hours and must not start a day until the previous day's "Done when" passes. Time budget is confirmed: 8–10 focused hours every day, Wed to Sun. Nothing is cut in advance, and the cut order applies only if a day's checks fail.

| Day | Build | Done when |
| --- | --- | --- |
| **Wed 25 (from afternoon)** | Repo scaffold, `CLAUDE.md`, docker-compose with pgvector, migration `001_init.sql`, Supabase project, `companies.csv` with 100+ verified slugs, Greenhouse + Lever + Ashby adapters with fixture tests, first `ingest.py` run | At least 1,000 active India/remote jobs in the DB; re-running ingest inserts 0 new rows |
| **Thu 26** | `extract.py` (Ollama backfill, then Groq), `embed.py`, hybrid search (keyword + vector + RRF) behind `/matches`, resume upload + parse + embed, start the 50 search queries | `/matches?q=python backend fresher` returns sensible results in under 1.5 s locally; at least 90% of jobs extracted and embedded |
| **Fri 27** | Reranker + personalisation + diversity + data-built reasons; agent loop with 5 tools, `AgentReply`, guardrail, logs; freeze the eval snapshot; label queries; `run_search_eval.py` | Search eval table prints all 5 variants; a scripted chat of 5 turns works end to end through `/chat` |
| **Sat 28** | Next.js mobile UI with day/night themes and brand tokens (sign-in, onboarding chips, cards with 👍/👎/Apply/Share on WhatsApp, chat), deploy API to HF Space and web to Vercel, GitHub Actions cron, digest email, `/stats`, rate limits, delete-my-data, agent and extraction evals | A friend on a phone completes the whole flow on the public URL; tomorrow's 02:00 IST ingest is scheduled; 5–10 friends onboarded |
| **Sun 29** | Morning: check that the nightly run and digest fired. Launch posts (see Launch). Fix the bugs users hit. Afternoon: README with architecture, eval table, usage numbers and a 2-minute demo video. Update the resume and the Elip application | At least 30 signups; README numbers match `/stats` and `eval/results.md`; resume bullets filled with real numbers |

Working rule for every day: commit after each task, push by night, and write a 3-line progress note in `PROGRESS.md` (done / broken / next).

## Risks and cut order

The biggest risk is breadth: a half-working agent hurts more than a solid search engine helps. When a day slips, cut from the top of this list and keep everything below it.

**Cut order (first to go → last):**

1. Email digest, replaced by a "New since yesterday" section in the app
2. Personalisation simulation eval (keep the search eval)
3. Ashby adapter (keep Greenhouse + Lever)
4. Chat UI polish; the agent can live behind one chat box
5. Personalisation (keep likes and dislikes logged, rank without them)
6. The agent itself. Never cut: ingestion, hybrid search + rerank, the search eval table, a public URL, real users

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Groq free limits hit during backfill or launch | High | Ollama backfill on the laptop; extraction only for changed jobs; per-user chat cap; 8B fallback; cache identical queries for 10 min |
| Too few Indian companies on these 3 ATSs | Medium | Add more slugs (YC India list, funded startups); include remote-friendly global startups that hire in India |
| Free API host too slow or out of RAM | Medium | Smaller reranker; rerank only the top 20; fall back to Render free or run the API on the laptop with a tunnel during the launch window |
| Free host sleeps, so the first load is slow | High | A loading state in the UI; a GitHub Actions ping every 30 min during launch hours |
| Job-board API shape differs from assumptions | Medium | Verify endpoints on day 1; one adapter per source with fixture tests |
| No real users by Sunday | Medium | Start onboarding friends Saturday; launch Sunday morning; a share button on every card |
| Looks like a clone of Elip | Low–medium | Pitch it as "I built a small version of your problem and measured it"; lead with the eval table and the lessons learned |

## Launch and promotion in India

The target is 30+ signups by Sunday night, through WhatsApp groups first and LinkedIn second, because that's where Indian students already are.

- **Saturday evening (soft launch):** send the link personally to 10–15 friends or batchmates on WhatsApp. Ask each for one 👎 reason or bug. Fix those before the public post.
- **Sunday morning:** post in LPU placement and batch WhatsApp groups. Send one short message with the link and a screenshot of a real match card, not a pitch deck. Something like: "Built a free tool that reads startup job boards every night and sends you 3 matches for your resume. Fresher-friendly filters. Try it, roast it."
- **Sunday midday:** a LinkedIn build-in-public post with the eval chart or table, the architecture image and the live link. Tag nobody you don't know.
- **In-product loop:** a "Share on WhatsApp" button on every card, with the app link, e.g. `?ref=wa_share` so shares are counted.
- **Track** signups by `ref` source (wa\_group, linkedin, wa\_share, direct) in `profiles.prefs.ref` or a `signups` field, so the README can say where users came from.

The landing page says plainly what is stored, why, and that it can be deleted. Never message people who didn't sign up.

## Instructions for Claude Code

Claude Code: this brief is the spec. Read it all, then plan the week before writing code.

1. **First output: a task list**, grouped by day as in the day-by-day plan. Each task is 1–2 hours with a one-line acceptance check. Show it to me and wait for my OK before coding.
2. **Copy this brief** into the repo as `docs/BRIEF.md`. Create a short `CLAUDE.md` holding the constraints (₹0, open-weight models only, public job-board APIs only, no invented numbers), the stack, the run commands and the cut order.
3. **Verify before you build:** confirm the three job-board endpoints and the current Groq model IDs and free limits from their official docs. Tell me about any difference from this brief before changing the design.
4. **Ask before:** adding any paid service or closed model, changing the stack, adding a dependency heavier than a few MB, or deleting data.
5. **Build in thin vertical slices:** each one runs end to end locally before the next. Prefer boring, readable code over abstractions. No agent frameworks.
6. **Tests:** write the tests listed under Deploy for each module as you build it. Keep `pytest` green before every commit.
7. **Commits:** small, with clear messages. Push at the end of each day. Never commit `.env` or keys.
8. **Evals and numbers:** build the eval scripts and the labelling CLI, but never generate ground-truth labels with an LLM. I label. Never write a metric into the README that a script didn't produce.
9. **Daily check-in:** at the end of each day, update `PROGRESS.md` and tell me what's done, what's broken, and whether we need to apply the cut order.
10. **If behind schedule:** say so early and propose which item from the cut order to drop. Don't silently skip things.

## Resume bullets and interview talking points

Fill every X from `eval/results.md` and `/stats` on Sunday night. If a number is weak, keep it and explain it. Honest numbers beat pretty ones in an interview.

**Resume entry: nightly, AI job-matching agent (Python, FastAPI, Postgres/pgvector, open-weight LLMs). Live link · GitHub**

- Built a nightly ingestion pipeline indexing X jobs from Y startup job boards (Greenhouse, Lever, Ashby), with incremental upserts, expiry, dedupe and LLM-based structured extraction (X% valid JSON).
- Designed hybrid search (Postgres full-text + pgvector HNSW, reciprocal rank fusion, cross-encoder reranking) that lifted NDCG@10 from X (keyword only) to Y on 50 hand-labelled queries, at X ms p95.
- Shipped a tool-calling agent with persistent preference memory and feedback-based personalisation, used by X students in its first days (X chats, X% 👍 rate); X% correct tool selection on a 40-case eval, 0 invented jobs.
- Ran entirely on free tiers and open-weight models, containerised with Docker, with scheduled ingestion and digests on GitHub Actions.

**Talking points to prepare:**

- Why hybrid beats either alone, with your own numbers, and which queries each one wins.
- How the index stays fresh: hashing, changed-only re-embedding, expiry and dedupe.
- Schema choices: why a generated `tsvector`, why HNSW, why partial indexes, RLS.
- How the agent is kept honest: tool-only job IDs, Pydantic validation, retry-then-fallback, logs.
- Free-tier engineering: how you designed around the rate limits.
- What you'd do at Elip's scale (\~16M listings): sharded or approximate indexes, a two-tower retrieval model trained on clicks, learning-to-rank on interaction logs, online A/B tests.
- One thing that surprised you in the eval, and what you changed because of it.
