-- Fixes two Supabase security-advisor warnings. Safe to run on local Postgres too.

-- 1. Pin skills_text's search_path so a caller can't shadow array_to_string.
--    pg_catalog is always searched first, so an empty path still resolves it.
alter function skills_text(text[]) set search_path = '';

-- 2. rls_auto_enable() is the helper Supabase adds for "Enable RLS on new tables
--    automatically". It is SECURITY DEFINER and was callable through /rest/v1/rpc
--    by anon and signed-in users. Its event trigger still fires without EXECUTE.
--    The function only exists on Supabase, so skip it elsewhere.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
  end if;
end $$;
