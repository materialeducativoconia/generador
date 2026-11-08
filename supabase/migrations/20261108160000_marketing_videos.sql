-- Promotional videos the team makes in /admin/marketing: a template, the tome it shows and the script DeepSeek wrote
-- (edited by hand). The MP4 is rendered in the admin's browser from these, so nothing else is stored.
create table if not exists public.marketing_videos (
  id uuid primary key default gen_random_uuid(),
  template text not null default 'topic_to_book',
  series_id uuid references public.series (id) on delete set null,
  format text not null default '9:16' check (format in ('9:16', '1:1', '16:9')),
  script jsonb not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists marketing_videos_created_idx on public.marketing_videos (created_at desc);
alter table public.marketing_videos enable row level security;
