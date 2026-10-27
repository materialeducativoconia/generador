-- Cover agent: an illustrated cover per tome, generated after the outline.
alter type public.job_kind add value if not exists 'cover';

alter table public.series
  add column cover_key text,   -- object in the public `covers` bucket
  add column cover jsonb;      -- {concept, palette, references, model, cost_usd}

-- Covers are shown in <img> tags, so a public bucket with unguessable keys (uuid per job).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('covers', 'covers', true, 10485760, array['image/png', 'image/jpeg', 'image/webp'])
on conflict (id) do nothing;
