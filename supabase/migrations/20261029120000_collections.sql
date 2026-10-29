-- Collections: the user groups tomes on the same topic by level ("Multiplicación", level 1, 2, 3…).
-- A tome belongs to at most one collection; deleting a collection leaves its tomes loose in the library.
create table public.collections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  description text check (char_length(description) <= 500),
  created_at timestamptz not null default now()
);
create index collections_user_idx on public.collections (user_id, created_at desc);
alter table public.collections enable row level security;
create policy "Users read their own collections" on public.collections for select to authenticated
  using ((select auth.uid()) = user_id);

alter table public.series add column collection_id uuid references public.collections (id) on delete set null;
alter table public.series add column collection_position integer;  -- order inside the collection: its level
create index series_collection_idx on public.series (collection_id, collection_position);
