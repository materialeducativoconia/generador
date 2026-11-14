-- First adopters: the team hands out links that give a plan free for some months (license_links); whoever opens one
-- and signs in with Google gets it (license_redemptions). What people do in the app (activity_events) and what they
-- tell the feedback bubble (feedback, written down with DeepSeek) are read in /admin to improve the app.
create table if not exists public.license_links (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  plan text not null default 'docente' check (plan in ('docente', 'creador', 'editorial')),
  months int not null default 3 check (months between 1 and 24),
  max_uses int not null default 1 check (max_uses between 1 and 1000),
  uses int not null default 0,
  note text not null default '',
  expires_at timestamptz,
  revoked_at timestamptz,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);
alter table public.license_links enable row level security;

create table if not exists public.license_redemptions (
  link_id uuid not null references public.license_links (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  org_id uuid not null references public.organizations (id) on delete cascade,
  redeemed_at timestamptz not null default now(),
  primary key (link_id, user_id)
);
create index if not exists license_redemptions_user_idx on public.license_redemptions (user_id);
alter table public.license_redemptions enable row level security;

create table if not exists public.activity_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  event text not null,
  path text,
  props jsonb not null default '{}',
  created_at timestamptz not null default now()
);
create index if not exists activity_events_user_idx on public.activity_events (user_id, created_at desc);
create index if not exists activity_events_event_idx on public.activity_events (event, created_at desc);
alter table public.activity_events enable row level security;

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users (id) on delete set null,
  kind text not null check (kind in ('problema', 'mejora', 'idea', 'elogio')),
  area text not null default '',
  summary text not null,
  detail text not null default '',
  severity text not null default 'media' check (severity in ('baja', 'media', 'alta')),
  path text,
  transcript jsonb not null default '[]',
  status text not null default 'nuevo' check (status in ('nuevo', 'visto', 'resuelto', 'descartado')),
  created_at timestamptz not null default now()
);
create index if not exists feedback_created_idx on public.feedback (created_at desc);
alter table public.feedback enable row level security;
