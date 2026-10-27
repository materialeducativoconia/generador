-- Tomes of any genre (coloring book, worksheet booklet, tutorial, lesson series).
-- The Architect agent picks the genre and writes the plan; the user only describes what they want.

alter table public.series
  alter column format drop not null,
  alter column lesson_duration_minutes drop not null,
  add column genre text,
  add column plan jsonb; -- Architect output: genre, style notes, research and image requests

-- Recomputes a series' status from its lessons. The worker calls it in the same
-- transaction that writes a lesson (ARCHITECTURE.md §4.4).
create function public.refresh_series_status(p_series_id uuid) returns void
language sql
set search_path = ''
as $$
  update public.series s
     set status = case
           when c.active > 0 then 'generating'
           when c.failed > 0 then 'needs_attention'
           else 'ready'
         end::public.series_status
    from (
      select count(*) filter (where status in ('pending', 'queued', 'generating')) as active,
             count(*) filter (where status = 'failed') as failed
        from public.lessons
       where series_id = p_series_id
    ) c
   where s.id = p_series_id
     and s.status in ('generating', 'needs_attention', 'ready');
$$;

revoke execute on function public.refresh_series_status(uuid) from public, anon, authenticated;
