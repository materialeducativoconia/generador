-- Art director: one style bible per tome (style, recurring characters, prompts), reused when a section is redone.
alter table public.series add column art jsonb;
