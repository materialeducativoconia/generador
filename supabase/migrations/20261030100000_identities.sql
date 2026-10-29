-- Identities (Mis identidades): the user's editorial lines. The identity job proposes three candidates
-- (Brand strategist + Identity designer + code guard); the user picks one and applies it to a collection,
-- so every tome of the collection shares its look, seal, voice and mascot. A loose tome may carry one too.
alter type public.job_kind add value if not exists 'identity';

create table public.identities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'generating' check (status in ('generating', 'choosing', 'ready', 'failed')),
  brief jsonb not null,                    -- what the user publishes, audience, personality words
  candidates jsonb not null default '[]',  -- three Designs, each with its brand
  design jsonb,                            -- the chosen Design (brand included): what tomes copy
  error text,
  created_at timestamptz not null default now()
);
create index identities_user_idx on public.identities (user_id, created_at desc);
alter table public.identities enable row level security;
create policy "Users read their own identities" on public.identities for select to authenticated
  using ((select auth.uid()) = user_id);

alter table public.collections add column identity_id uuid references public.identities (id) on delete set null;
alter table public.series add column identity_id uuid references public.identities (id) on delete set null;

-- The identity job's LLM calls belong to the user's library, not to a tome.
alter table public.generation_logs alter column series_id drop not null;
