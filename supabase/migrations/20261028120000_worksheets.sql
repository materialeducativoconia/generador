-- Phase 8: literacy worksheets. Sections remember the letters they teach (the decodable-text check), and the
-- asset library gets a kind for worksheet pictures: one plain drawing per word, shared by every tome.
alter table public.lessons add column letters jsonb not null default '[]';
alter table public.assets drop constraint assets_kind_check;
alter table public.assets add constraint assets_kind_check
  check (kind in ('line_art', 'illustration', 'photo', 'diagram', 'icon'));
