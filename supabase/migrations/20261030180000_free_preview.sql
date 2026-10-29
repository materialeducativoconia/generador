-- Free preview instead of free credits. A visitor writes their request on the landing page as an anonymous
-- Supabase user and gets, at our cost, the outline, the design, the illustrated cover and a sample of the first
-- section. Downloading and the rest of the tome need a plan. Signing in with Google redeems a claim code that
-- moves the preview to the real account.
alter table public.profiles alter column email drop not null;  -- anonymous users have none

-- One free preview per organization. Existing organizations had the 40-credit trial instead.
alter table public.organizations add column free_preview_at timestamptz;
update public.organizations set free_preview_at = now();

alter table public.series
  add column preview boolean not null default false,
  add column preview_ip text;  -- caps free previews per visitor and per day
create index series_preview_idx on public.series (created_at) where preview;

alter table public.lessons add column sample boolean not null default false;  -- the preview's first pages only

create table public.claims (
  code text primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,  -- the anonymous user
  created_at timestamptz not null default now()
);
alter table public.claims enable row level security;

-- New users no longer get trial credits; anonymous users get a profile and an organization like everyone else.
create or replace function public.handle_new_user() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  org uuid;
begin
  insert into public.profiles (id, email, display_name, avatar_url)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'),
    coalesce(new.raw_user_meta_data ->> 'avatar_url', new.raw_user_meta_data ->> 'picture')
  );
  insert into public.organizations (name)
  values (coalesce(new.raw_user_meta_data ->> 'full_name', new.email, 'Invitado')) returning id into org;
  insert into public.memberships (org_id, user_id, role) values (org, new.id, 'owner');
  return new;
end;
$$;
