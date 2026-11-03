-- Reescribir el texto: a version of an illustrated tome with its words rewritten over the same pictures.
alter type public.job_kind add value if not exists 'rewrite';
alter table public.series drop constraint if exists series_variant_check;
alter table public.series add constraint series_variant_check check (variant in ('style', 'story', 'next', 'text'));
