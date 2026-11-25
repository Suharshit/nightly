-- Local only: a stand-in for the Supabase auth schema, so 001_init.sql runs unchanged.
-- Never apply this to Supabase.
create schema if not exists auth;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text
);
create or replace function auth.uid() returns uuid
language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
do $$ begin
  create role authenticated nologin;
exception when duplicate_object then null; end $$;
