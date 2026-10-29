-- Owner-approved 2026-10-29 (docs/LAUNCH_READINESS_REVIEW_2026-10-29.md, F1 + F2).
-- Run in Supabase: Dashboard -> SQL Editor -> paste -> Run. Safe to re-run.
-- Precondition checked 2026-10-29: the only non-system login role is postgres, which owns all
-- 31 public tables; the frontend uses Supabase only for auth (no .from/.rpc/storage calls).

-- F1: the event-trigger function need not be callable over /rest/v1/rpc.
revoke execute on function public.rls_auto_enable() from anon, authenticated, public;

-- F2: the public API roles lose table privileges (RLS was already denying them).
revoke all on all tables in schema public from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;

-- Check afterwards (expect only postgres and service_role):
select grantee, count(distinct table_name) from information_schema.role_table_grants
where table_schema = 'public' group by 1 order by 1;
