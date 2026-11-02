-- The free plate library: pictures we paid for (the style lab) published by the team, each with its question and
-- answer, downloadable as a printable PDF after signing in. Only the API reads or writes it.
create table public.library_plates (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  title text not null,                  -- the plate's question, e.g. "¿Por qué brilla el Sol?"
  answer text not null default '',
  topic text not null,                  -- e.g. "El sistema solar"
  audience text not null default '',
  style text not null,                  -- app.house_styles key
  image_key text not null,              -- images bucket
  pdf_key text,                         -- exports bucket, made on the first download
  sample_id uuid references public.style_samples (id) on delete set null,
  downloads integer not null default 0,
  published boolean not null default true,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);
create index library_plates_published_idx on public.library_plates (published, created_at desc);
alter table public.library_plates enable row level security;
