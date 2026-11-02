-- The character maker: users with a plan describe a character and the worker designs and paints its model sheet.
alter type public.job_kind add value if not exists 'character';
alter table public.characters
  add column status text not null default 'ready' check (status in ('painting', 'ready', 'failed')),
  add column description text,          -- what the user asked for
  add column error text;
alter table public.characters alter column look drop not null;
alter table public.characters alter column archetype drop not null;

-- A character's model sheet redrawn in each house style it has been used in (app.house_styles).
create table public.character_sheets (
  character_id uuid not null references public.characters (id) on delete cascade,
  style text not null,
  sheet_key text not null,
  created_at timestamptz not null default now(),
  primary key (character_id, style)
);
alter table public.character_sheets enable row level security;

-- The guide the user picked for a tome; null lets the casting director choose.
alter table public.series add column guide_id uuid references public.characters (id) on delete set null;
