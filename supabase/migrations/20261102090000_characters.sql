-- The character library: recurring guides for picture books, each with a model sheet (turnaround and
-- expressions) the Illustrator uses as reference. Characters created for paid tomes are shared and grow the
-- library; new characters can be based on earlier ones. Only the API (service role) reads or writes it.
create table public.characters (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  role text not null default 'guide' check (role in ('guide', 'companion')),
  archetype text not null,              -- e.g. "niña exploradora", "robot amigable"
  look text not null,                   -- English: the fixed appearance repeated in every prompt
  personality text not null default '',
  signature text not null default '',   -- the detail that is always there (a yellow scarf, round glasses)
  palette text[] not null default '{}',
  style text not null default '',       -- the art style its sheet was painted in
  topics text[] not null default '{}',  -- normalized subjects it has appeared in
  audience text not null default '',
  sheet_key text,                       -- images bucket: the model sheet
  based_on uuid references public.characters (id) on delete set null,
  user_id uuid references auth.users (id) on delete set null,
  shared boolean not null default true, -- false: a brand mascot or a licensed character, never lent to others
  seed boolean not null default false,  -- one of the starter characters the worker paints
  use_count integer not null default 0,
  created_at timestamptz not null default now()
);
create index characters_shared_idx on public.characters (shared, use_count desc);
alter table public.characters enable row level security;

-- The tome's cast: [{character_id, name, role, look, signature, sheet_key}], chosen before the cover.
alter table public.series add column "cast" jsonb;
