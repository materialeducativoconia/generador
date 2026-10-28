-- Phase 4: print editions ship a second file (the KDP cover wrap) and a print preflight report;
-- colouring pages are stored as vector SVG.
alter table public.exports
  add column cover_storage_key text,
  add column preflight jsonb;

update storage.buckets set allowed_mime_types = array['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml']
 where id = 'images';
