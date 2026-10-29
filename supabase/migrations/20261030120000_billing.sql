-- Plans and credits. Every user belongs to an organization (alone, for now): plans, credits and Stripe live on
-- the organization so Editorial teams and future sub-apps need no rework. Three role layers stay apart:
-- profiles.platform_role (our staff), memberships.role (inside an organization), subscriptions.plan (per app).
create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 120),
  stripe_customer_id text unique,
  created_at timestamptz not null default now()
);
alter table public.organizations enable row level security;

create table public.memberships (
  org_id uuid not null references public.organizations (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  role text not null default 'owner' check (role in ('owner', 'editor', 'viewer')),
  created_at timestamptz not null default now(),
  primary key (org_id, user_id)
);
create index memberships_user_idx on public.memberships (user_id);
alter table public.memberships enable row level security;

alter table public.profiles add column platform_role text not null default 'user'
  check (platform_role in ('user', 'staff', 'admin'));

-- One subscription per organization and app (this generator is app 'generador'). No row = the free trial.
create table public.subscriptions (
  org_id uuid not null references public.organizations (id) on delete cascade,
  app text not null default 'generador',
  plan text not null check (plan in ('docente', 'creador', 'editorial')),
  status text not null,                  -- Stripe's: active, past_due, canceled…
  stripe_subscription_id text unique,
  current_period_end timestamptz,
  updated_at timestamptz not null default now(),
  primary key (org_id, app)
);
alter table public.subscriptions enable row level security;

-- Credits come in buckets: the month's plan credits (expire at the period end), packs (12 months), the trial.
-- Spending takes plan credits first, then the bucket that expires soonest.
create table public.credit_buckets (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations (id) on delete cascade,
  source text not null check (source in ('plan', 'pack', 'trial', 'adjust')),
  granted integer not null check (granted >= 0),
  remaining integer not null check (remaining >= 0),
  expires_at timestamptz,
  stripe_ref text unique,                -- the invoice or checkout that paid for it: webhooks are idempotent
  created_at timestamptz not null default now()
);
create index credit_buckets_org_idx on public.credit_buckets (org_id, expires_at);
alter table public.credit_buckets enable row level security;

-- Append-only history: every grant, spend, refund and expiry, tied to the job that spent it.
create table public.credit_ledger (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations (id) on delete cascade,
  user_id uuid references public.profiles (id) on delete set null,
  bucket_id uuid references public.credit_buckets (id) on delete set null,
  delta integer not null,
  kind text not null check (kind in ('grant', 'spend', 'refund', 'expire')),
  reason text not null,
  job_id uuid,
  created_at timestamptz not null default now()
);
create index credit_ledger_org_idx on public.credit_ledger (org_id, created_at desc);
create index credit_ledger_job_idx on public.credit_ledger (job_id) where job_id is not null;
alter table public.credit_ledger enable row level security;

create table public.stripe_events (
  id text primary key,
  type text not null,
  received_at timestamptz not null default now()
);
alter table public.stripe_events enable row level security;

-- Sign-up now also opens the user's organization with 40 trial credits (one complete tome).
create or replace function public.handle_new_user() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  org uuid;
  bucket uuid;
begin
  insert into public.profiles (id, email, display_name, avatar_url)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'),
    coalesce(new.raw_user_meta_data ->> 'avatar_url', new.raw_user_meta_data ->> 'picture')
  );
  insert into public.organizations (name)
  values (coalesce(new.raw_user_meta_data ->> 'full_name', new.email)) returning id into org;
  insert into public.memberships (org_id, user_id, role) values (org, new.id, 'owner');
  insert into public.credit_buckets (org_id, source, granted, remaining) values (org, 'trial', 40, 40)
    returning id into bucket;
  insert into public.credit_ledger (org_id, user_id, bucket_id, delta, kind, reason)
  values (org, new.id, bucket, 40, 'grant', 'Prueba gratis');
  return new;
end;
$$;

-- Existing users get the same.
do $$
declare
  p record;
  org uuid;
  bucket uuid;
begin
  for p in select id, coalesce(display_name, email) as name from public.profiles
            where id not in (select user_id from public.memberships) loop
    insert into public.organizations (name) values (p.name) returning id into org;
    insert into public.memberships (org_id, user_id, role) values (org, p.id, 'owner');
    insert into public.credit_buckets (org_id, source, granted, remaining) values (org, 'trial', 40, 40)
      returning id into bucket;
    insert into public.credit_ledger (org_id, user_id, bucket_id, delta, kind, reason)
    values (org, p.id, bucket, 40, 'grant', 'Prueba gratis');
  end loop;
end;
$$;

-- Credits are the real limit now; the daily section cap stays only as a hidden guard against abuse.
alter table public.profiles alter column daily_lesson_quota set default 300;
update public.profiles set daily_lesson_quota = 300 where daily_lesson_quota < 300;
