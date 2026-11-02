-- The tome a style sample was painted from, so a failed style can be painted again with the same cast.
alter table public.style_samples add column series_id uuid references public.series (id) on delete set null;
