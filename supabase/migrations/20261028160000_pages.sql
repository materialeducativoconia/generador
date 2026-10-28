-- Material ordered by page count: the tome's target and each section's share of it.
alter table public.series add column page_target integer check (page_target between 4 and 200);
alter table public.lessons add column pages integer check (pages between 1 and 60);
