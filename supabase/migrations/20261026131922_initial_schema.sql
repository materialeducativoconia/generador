-- Initial schema for the generador (see ARCHITECTURE.md §4).
--
-- Access model: the browser talks to Supabase only for Auth and Realtime. Every
-- business write goes through our API, which connects as a server role that
-- bypasses RLS. So `authenticated` gets SELECT on its own rows (needed by
-- Realtime, and defence in depth) and nothing else; `anon` gets nothing.

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

create type public.series_format as enum ('lesson_series', 'workbook');

create type public.series_status as enum (
  'outlining', 'outline_ready', 'outline_failed', 'generating', 'needs_attention', 'ready'
);

create type public.lesson_status as enum (
  'pending', 'queued', 'generating', 'generated', 'failed', 'edited', 'approved'
);

create type public.job_kind as enum ('outline', 'lesson', 'lesson_block', 'pdf_export');

create type public.job_status as enum ('queued', 'running', 'succeeded', 'failed', 'cancelled');

create type public.export_status as enum ('queued', 'running', 'succeeded', 'failed');

create type public.generation_outcome as enum (
  'ok', 'rate_limited', 'upstream_error', 'timeout', 'invalid_output', 'truncated', 'auth_error'
);

-- ---------------------------------------------------------------------------
-- Shared trigger: keep updated_at current
-- ---------------------------------------------------------------------------

create function public.set_updated_at() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- profiles: our "User", 1:1 with auth.users (Google sign-in only)
-- ---------------------------------------------------------------------------

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  display_name text,
  avatar_url text,
  daily_lesson_quota integer not null default 60 check (daily_lesson_quota >= 0),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger profiles_set_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();

-- The first Google login creates the auth.users row; that is the sign-up.
-- Later changes to the Google name are not copied: the teacher may have edited display_name.
create function public.handle_new_user() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email, display_name, avatar_url)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'),
    coalesce(new.raw_user_meta_data ->> 'avatar_url', new.raw_user_meta_data ->> 'picture')
  );
  return new;
end;
$$;

revoke execute on function public.handle_new_user() from public, anon, authenticated;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- series
-- ---------------------------------------------------------------------------

create table public.series (
  id uuid primary key default gen_random_uuid(), -- the API passes UUIDv7 ids
  user_id uuid not null references public.profiles (id) on delete cascade,
  title text,
  topic text not null,
  audience jsonb not null,
  language text not null,
  format public.series_format not null,
  lesson_count smallint not null check (lesson_count between 1 and 20),
  lesson_duration_minutes smallint not null check (lesson_duration_minutes between 5 and 240),
  extra_instructions text,
  status public.series_status not null,
  outline_approved_at timestamptz,
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index series_user_id_idx on public.series (user_id);

create trigger series_set_updated_at before update on public.series
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- lessons
-- ---------------------------------------------------------------------------

create table public.lessons (
  id uuid primary key default gen_random_uuid(),
  series_id uuid not null references public.series (id) on delete cascade,
  position smallint not null check (position >= 1),
  title text not null,
  objectives jsonb not null,
  key_points jsonb not null,
  content_json jsonb,
  pending_content_json jsonb,
  status public.lesson_status not null,
  content_version integer not null default 0,
  last_error jsonb,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Deferrable so the outline can be reordered inside one transaction.
  constraint lessons_series_position_key unique (series_id, position) deferrable initially immediate
);

create index lessons_series_status_idx on public.lessons (series_id, status);

create trigger lessons_set_updated_at before update on public.lessons
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- generation_jobs: the work queue and the state the UI shows
-- ---------------------------------------------------------------------------

create table public.generation_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  series_id uuid not null references public.series (id) on delete cascade,
  lesson_id uuid references public.lessons (id) on delete cascade,
  kind public.job_kind not null,
  status public.job_status not null,
  payload jsonb not null,
  attempts smallint not null default 0,
  max_attempts smallint not null default 4,
  run_after timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  error jsonb,
  idempotency_key text,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint generation_jobs_idempotency_key unique (user_id, idempotency_key)
);

-- Keeps "claim the next job" O(log n) no matter how much history accumulates.
create index generation_jobs_queued_idx on public.generation_jobs (run_after) where status = 'queued';
create index generation_jobs_series_idx on public.generation_jobs (series_id);
create index generation_jobs_user_created_idx on public.generation_jobs (user_id, created_at); -- daily quota

create trigger generation_jobs_set_updated_at before update on public.generation_jobs
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- generation_logs: one row per HTTP call to DeepSeek
-- ---------------------------------------------------------------------------

create table public.generation_logs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.generation_jobs (id) on delete cascade,
  -- Denormalised for analytics without joins.
  user_id uuid not null,
  series_id uuid not null,
  lesson_id uuid,
  attempt smallint not null,
  model text not null,
  prompt_version text not null,
  request_messages jsonb, -- nulled after 30 days
  response_text text,     -- nulled after 30 days
  finish_reason text,
  prompt_tokens integer,
  completion_tokens integer,
  prompt_cache_hit_tokens integer,
  prompt_cache_miss_tokens integer,
  cost_usd_micros bigint,
  latency_ms integer,
  time_to_first_token_ms integer,
  http_status smallint,
  outcome public.generation_outcome not null,
  created_at timestamptz not null default now()
);

create index generation_logs_job_idx on public.generation_logs (job_id);
create index generation_logs_created_idx on public.generation_logs (created_at); -- retention sweep

-- ---------------------------------------------------------------------------
-- exports: generated PDFs (files live in the `exports` storage bucket)
-- ---------------------------------------------------------------------------

create table public.exports (
  id uuid primary key default gen_random_uuid(),
  series_id uuid not null references public.series (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  job_id uuid references public.generation_jobs (id) on delete set null,
  status public.export_status not null,
  options jsonb not null,
  content_hash text,
  storage_key text, -- {user_id}/{series_id}/{export_id}.pdf
  page_count integer,
  size_bytes bigint,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index exports_series_idx on public.exports (series_id);
create index exports_content_hash_idx on public.exports (content_hash);

create trigger exports_set_updated_at before update on public.exports
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Privileges and Row Level Security
-- ---------------------------------------------------------------------------

-- Supabase grants everything on public tables to anon and authenticated by default.
-- Take it all back, here and for tables created by later migrations.
revoke all on all tables in schema public from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;

grant select on public.profiles, public.series, public.lessons, public.generation_jobs, public.exports
  to authenticated;
-- generation_logs: no grant at all; it holds raw prompts and responses.

alter table public.profiles enable row level security;
alter table public.series enable row level security;
alter table public.lessons enable row level security;
alter table public.generation_jobs enable row level security;
alter table public.generation_logs enable row level security;
alter table public.exports enable row level security;

create policy "Users read their own profile" on public.profiles
  for select to authenticated using (id = (select auth.uid()));

create policy "Users read their own series" on public.series
  for select to authenticated using (user_id = (select auth.uid()));

create policy "Users read lessons of their own series" on public.lessons
  for select to authenticated using (
    exists (select 1 from public.series s where s.id = series_id and s.user_id = (select auth.uid()))
  );

create policy "Users read their own jobs" on public.generation_jobs
  for select to authenticated using (user_id = (select auth.uid()));

create policy "Users read their own exports" on public.exports
  for select to authenticated using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- Realtime: the browser listens to job changes as a "refetch /progress" signal
-- ---------------------------------------------------------------------------

alter publication supabase_realtime add table public.generation_jobs;

-- ---------------------------------------------------------------------------
-- Storage: private bucket for PDFs. No policies: only the service role uploads,
-- and only the API signs download URLs.
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('exports', 'exports', false, 52428800, array['application/pdf']);
