-- Phase 2: the Illustrator fills image blocks; generated images go to a library shared by every tome,
-- so the Curator can reuse "una ardilla para colorear" instead of paying for it twice.
alter type public.job_kind add value if not exists 'illustration';

create extension if not exists pg_trgm with schema extensions;

create table public.assets (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('line_art', 'illustration', 'photo', 'diagram')),
  subject text not null,
  subject_norm text not null,       -- lowercased, no accents or articles: what the Curator matches on
  style_key text not null,          -- line art is style-free ('line'); colour art depends on theme and palette
  storage_key text not null,        -- object in the public `images` bucket
  media_type text not null,
  model text,
  cost_usd numeric,
  review jsonb,                     -- the Reviewer's verdict
  created_by uuid references public.profiles (id) on delete set null,
  use_count integer not null default 1,
  created_at timestamptz not null default now()
);

create index assets_subject_trgm_idx on public.assets using gin (subject_norm extensions.gin_trgm_ops);
create index assets_kind_style_idx on public.assets (kind, style_key);

-- Server-only table: RLS on with no policies, so the anon and authenticated roles can't read it.
alter table public.assets enable row level security;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('images', 'images', true, 10485760, array['image/png', 'image/jpeg', 'image/webp'])
on conflict (id) do nothing;
