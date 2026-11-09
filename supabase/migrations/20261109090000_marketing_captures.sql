-- Real screenshots of the app for the promotional videos: each shown in a device frame, the camera zooming to its
-- marked points. Kept in the marketing bucket, which now takes images too.
update storage.buckets set allowed_mime_types = array['video/mp4', 'video/webm', 'image/png', 'image/jpeg', 'image/webp']
 where id = 'marketing';

create table if not exists public.marketing_captures (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text not null default '',
  image_key text not null,
  width int not null check (width > 0),
  height int not null check (height > 0),
  focus jsonb not null default '[]',  -- [{x, y, label}]: x and y are fractions of the image
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);
alter table public.marketing_captures enable row level security;
