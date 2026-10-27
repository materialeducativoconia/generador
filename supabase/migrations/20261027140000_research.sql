-- Phase 3: the Researcher's fact sheet per tome, and attribution for library photos (Wikimedia Commons).
alter table public.series add column research jsonb;   -- {needed, queries, facts: [{text, source}], sources: [...]}
alter table public.assets add column attribution jsonb; -- {author, license, source_url} for photos we did not make
