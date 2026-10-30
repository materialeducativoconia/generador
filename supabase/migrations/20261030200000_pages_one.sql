-- Pages are content pages now (cover, index and answer key come on top): a one-page tome is valid.
alter table public.series drop constraint series_page_target_check;
alter table public.series add constraint series_page_target_check check (page_target between 1 and 200);
