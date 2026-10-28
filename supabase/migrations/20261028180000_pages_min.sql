-- Material can be as short as 3 pages.
alter table public.series drop constraint series_page_target_check;
alter table public.series add constraint series_page_target_check check (page_target between 3 and 200);
