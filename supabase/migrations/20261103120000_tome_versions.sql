-- Another version of a tome: in another illustration style, with a changed story or content, or the next tome of
-- its series. The new tome remembers where it came from; the original is never touched.
alter table public.series
  add column if not exists source_id uuid references public.series(id) on delete set null,
  add column if not exists variant text check (variant in ('style', 'story', 'next'));

create index if not exists series_source_id_idx on public.series (source_id) where source_id is not null;
