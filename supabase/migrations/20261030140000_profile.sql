-- Profile: how the user signs their material. "Elaborado por" prints author_name (or the Google name) and the
-- school; the organization's logo (Creador and up) prints beside it. Logos live in the public `covers` bucket.
alter table public.profiles
  add column author_name text check (char_length(author_name) <= 80),
  add column school text check (char_length(school) <= 120);
alter table public.organizations add column logo_key text;
