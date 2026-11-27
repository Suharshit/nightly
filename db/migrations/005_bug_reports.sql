-- Bug reports sent from the app's /bug page; the owner reads them on /stats.
-- Only the API (service connection) touches this table: RLS on, no rights for anon or
-- signed-in browser roles.
create table if not exists bug_reports (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  user_id uuid references auth.users(id) on delete set null,
  email text,                         -- optional, only to reply; cleared by "Delete my data"
  page text,                          -- where it happened, e.g. /feed
  message text not null check (char_length(message) between 5 and 2000),
  user_agent text,
  status text not null default 'open' check (status in ('open', 'fixed', 'wontfix'))
);
create index if not exists bug_reports_created on bug_reports (created_at desc);
alter table bug_reports enable row level security;
revoke all on bug_reports from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on bug_reports from anon, authenticated;
  end if;
end $$;
