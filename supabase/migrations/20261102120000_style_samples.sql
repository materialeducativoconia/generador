-- The style lab: one subject painted in every house style so the team picks each style's reference images.
create table public.style_samples (
  id uuid primary key default gen_random_uuid(),
  run uuid not null,
  style text not null,
  subject text not null,
  status text not null default 'painting' check (status in ('painting', 'done', 'failed')),
  raw_key text,                         -- images bucket: the painting as the model returned it
  key text,                             -- images bucket: after finishing (grain, palette)
  error text,
  cost_usd numeric,
  chosen boolean not null default false, -- a reference image of its style
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);
create index style_samples_run_idx on public.style_samples (created_at desc, run);
alter table public.style_samples enable row level security;
