-- nightly: core schema. Runs on Supabase and on local Postgres (with db/local/000_auth_stub.sql).
create extension if not exists vector;
create extension if not exists pg_trgm;

-- array_to_string is only STABLE, and generated columns need IMMUTABLE expressions.
-- Joining a text[] with a fixed separator is deterministic, so this wrapper is safe.
create or replace function skills_text(text[]) returns text
language sql immutable parallel safe as $$ select array_to_string($1, ' ') $$;

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
  canonical_id bigint references jobs(id),      -- null = this row is canonical
  title text not null,
  location_raw text,
  remote boolean default false,
  city text,
  work_mode text,               -- onsite | hybrid | remote
  seniority text,               -- intern | fresher | junior | mid | senior
  employment_type text,
  min_exp_years int,
  max_exp_years int,
  skills text[] default '{}',
  salary_raw text,
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
    setweight(to_tsvector('english', skills_text(skills)), 'B') ||
    setweight(to_tsvector('english', coalesce(description_text,'')), 'C')
  ) stored,
  unique (source, external_id)
);
-- Feed and filters: only active rows, newest first.
create index jobs_active_idx on jobs (is_active, posted_at desc) where is_active;
-- Keyword retrieval.
create index jobs_tsv_idx on jobs using gin (tsv);
-- Vector retrieval (approximate nearest neighbour, cosine).
create index jobs_emb_idx on jobs using hnsw (embedding vector_cosine_ops);
-- Skill filters and overlap.
create index jobs_skills_idx on jobs using gin (skills);
-- Work queues for extract.py and embed.py.
create index jobs_pending_idx on jobs (id) where extraction_status = 'pending';

create table profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text,
  resume_text text,
  resume_embedding vector(384),
  prefs jsonb default '{}',     -- roles, cities, work_mode, seniority, must_skills, avoid, ref
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
create index messages_user_idx on messages (user_id, created_at desc);

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

-- Row Level Security: a signed-in user reads only their own rows.
-- The API uses the service role key, which bypasses RLS.
alter table profiles enable row level security;
alter table interactions enable row level security;
alter table messages enable row level security;
create policy own_profile on profiles for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy own_interactions on interactions for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy own_messages on messages for all to authenticated
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
