-- Phase 7: what each tome cost. Assets remember the tome that paid for them (shared colouring pages are
-- reused by other tomes for free); covers keep a running total in series.cover->spent_usd.
alter table public.assets add column series_id uuid references public.series (id) on delete set null;
create index assets_series_idx on public.assets (series_id);
