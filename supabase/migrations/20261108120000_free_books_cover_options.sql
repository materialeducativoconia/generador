-- The free book library on the landing: whole tomes the team publishes from the admin, shown as page thumbnails and
-- downloaded as their PDF after signing in. Only the API reads or writes it.
create table if not exists public.library_books (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  series_id uuid not null unique references public.series (id) on delete cascade,
  title text not null,
  topic text not null,
  audience text not null default '',
  genre text,
  page_count integer not null default 0,
  pages jsonb not null default '[]'::jsonb,  -- images bucket keys of the first pages' thumbnails, the cover first
  pdf_key text not null,                     -- exports bucket: a copy of the tome's PDF when it was published
  downloads integer not null default 0,
  published boolean not null default true,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);
create index if not exists library_books_published_idx on public.library_books (published, created_at desc);
alter table public.library_books enable row level security;

-- What a tome's cover prints besides its title, as the user set it in the page editor (app.content.CoverOptions).
alter table public.series add column if not exists cover_options jsonb not null default '{}'::jsonb;
