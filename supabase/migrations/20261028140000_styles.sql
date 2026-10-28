-- Phase 9: the user's style library. A user uploads reference PDFs or images (private `references` bucket);
-- the style job samples pages, a vision model picks the best-designed ones and extracts their style, and
-- code turns it into a layout theme the Designer can use for any of the user's tomes.
alter type public.job_kind add value if not exists 'style';

create table public.styles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  status text not null default 'uploading' check (status in ('uploading', 'analyzing', 'ready', 'failed')),
  source_key text not null,          -- the upload in `references`
  source_type text not null,         -- application/pdf, image/png, image/jpeg, image/webp
  pages jsonb not null default '[]', -- storage keys of the sampled pages (public `images` bucket, small JPEGs)
  spec jsonb,                        -- the Style analyst's reading of the references
  design jsonb,                      -- the Theme maker's output: a Design the template can render
  error text,
  created_at timestamptz not null default now()
);
create index styles_user_idx on public.styles (user_id, created_at desc);
alter table public.styles enable row level security;
create policy "Users read their own styles" on public.styles for select to authenticated
  using ((select auth.uid()) = user_id);

alter table public.series add column style_id uuid references public.styles (id) on delete set null;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('references', 'references', false, 52428800,
        array['application/pdf', 'image/png', 'image/jpeg', 'image/webp'])
on conflict (id) do nothing;

-- A style job belongs to the user's library, not to a tome.
alter table public.generation_jobs alter column series_id drop not null;
