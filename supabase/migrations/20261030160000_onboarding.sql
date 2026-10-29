-- Onboarding: what the user told us on the first visit (use, levels, subjects) shapes their first tome and
-- feeds analytics. onboarded_at null = show the welcome flow; users who already made a tome skip it.
alter table public.profiles
  add column onboarding jsonb,
  add column onboarded_at timestamptz;
update public.profiles p set onboarded_at = now()
 where exists (select 1 from public.series s where s.user_id = p.id);
