-- The shared premium library and cached previews: what paying users' tomes paint becomes art any visitor's preview
-- may use, and a finished preview is served again to the next visitor who asks for the same thing.

alter table public.assets
  add column library boolean not null default false,  -- premium art from a bought tome, without a brand: shareable
  add column draft boolean not null default false,    -- a preview's low-resolution art, upscaled when the tome is bought
  add column aspect text,                             -- 3:4, 4:3, 1:1: a library picture fits only its own shape
  add column topic_norm text;                         -- the tome's topic, normalized: a second clue for matching

create index assets_library_idx on public.assets (kind, aspect) where library;
create index assets_topic_trgm_idx on public.assets using gin (topic_norm extensions.gin_trgm_ops) where library;

-- Art already painted for bought tomes, without a brand mascot, joins the library.
update public.assets a
   set library = true, topic_norm = lower(coalesce(s.title, s.topic))
  from public.series s
 where a.series_id = s.id and not s.preview and a.kind in ('illustration', 'line_art')
   and s.design #> '{brand,mascot}' is null;

alter table public.series
  add column preview_key text,       -- request, audience, format and size, normalized: identical requests share a preview
  add column cloned_from uuid references public.series (id) on delete set null;

create index series_preview_key_idx on public.series (preview_key) where preview_key is not null;
